#!/usr/bin/env python3
"""Read-only checker for the Slime fixture formats.

Checks staged folders and index slices, provider advertisements, query responses,
notices, and route pins. No network, extraction, signing, or credential access.
This is not a production importer or a complete Pubky client.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
ALPHABET = 'ybndrfg8ejkmcpqxot1uwisza345h769'
CONTROL = {'set.json', 'set.sig.json'}
LIMITS = {'set': 16*1024*1024, 'signature': 8192, 'record': 65536, 'observation': 65536,
          'provider': 65536, 'slice': 16*1024*1024, 'candidates': 4*1024*1024,
          'notice': 8192, 'route': 65536}
EXAMPLE = '/pub/slime-example/'
LIVE_ROLES = {'records', 'query', 'notices'}

class InvalidSet(ValueError):
    """Invalid, unsupported, incomplete, or over-budget fixture."""

def _registry() -> Registry:
    resources = []
    for path in sorted((ROOT/'schemas').glob('*.schema.json')):
        schema = json.loads(path.read_text())
        if '$id' in schema:
            resources.append((schema['$id'], Resource.from_contents(schema)))
    return Registry().with_resources(resources)

REGISTRY = _registry()

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise InvalidSet('Duplicate JSON key: '+key)
        result[key] = value
    return result

def reject_constant(value):
    raise InvalidSet('Non-finite JSON number: '+value)

def load_json(data: bytes):
    if data.startswith(b'\xef\xbb\xbf'):
        raise InvalidSet('UTF-8 BOM')
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject_constant)
    except InvalidSet:
        raise
    except Exception as exc:
        raise InvalidSet(f'Invalid JSON: {exc}') from exc

def parse(data: bytes, kind: str):
    if len(data) > LIMITS[kind] or data.startswith(b'\xef\xbb\xbf'):
        raise InvalidSet('Control-file size limit or UTF-8 BOM')
    try:
        result = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject_constant)
        schema = json.loads((ROOT/'schemas'/f'{kind}.schema.json').read_text())
        Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker()).validate(result)
        return result
    except InvalidSet:
        raise
    except Exception as exc:
        raise InvalidSet(f'Invalid {kind} JSON: {exc}') from exc

def key_encode(raw: bytes) -> str:
    n = int.from_bytes(raw, 'big') << 4
    return ''.join(ALPHABET[(n >> (5*(51-i))) & 31] for i in range(52))

def key_decode(text: str) -> bytes:
    if len(text)!=52 or any(c not in ALPHABET for c in text):
        raise InvalidSet('Invalid public key encoding')
    n=0
    for c in text:
        n=(n<<5) | ALPHABET.index(c)
    if n & 15:
        raise InvalidSet('Noncanonical public key padding')
    raw=(n>>4).to_bytes(32,'big')
    if key_encode(raw)!=text:
        raise InvalidSet('Noncanonical key')
    return raw

def safe_path(name: str) -> None:
    if len(name)>512 or not re.fullmatch(r'[A-Za-z0-9_./-]+',name):
        raise InvalidSet('Unsafe filename: '+name)
    for segment in name.split('/'):
        stem=segment.split('.')[0].upper()
        if (not segment or len(segment)>128 or segment in {'.','..'} or segment.endswith('.')
            or stem in {'CON','PRN','AUX','NUL'} or re.fullmatch(r'(COM|LPT)[1-9]',stem)):
            raise InvalidSet('Unsafe path segment: '+segment)

def origin_author(uri: str) -> str:
    u=urlsplit(uri)
    if u.scheme!='pubky' or u.netloc!=u.hostname or u.query or u.fragment or not u.path.startswith('/pub/'):
        raise InvalidSet('Unsupported author-origin URI')
    key_decode(u.netloc)
    return u.netloc

def authority(uri: str) -> str:
    """Key of a pubky URI, including a bare key URI such as pubky://<key>/."""
    u=urlsplit(uri)
    if u.scheme!='pubky' or u.query or u.fragment:
        raise InvalidSet('Not a pubky URI: '+uri)
    key_decode(u.netloc)
    return u.netloc

def host_of(uri: str) -> str|None:
    u=urlsplit(uri)
    return u.hostname if u.scheme in {'http','https'} else None

def timestamp(text: str) -> datetime:
    return datetime.strptime(text, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)

def verify_signature(payload: bytes, sidecar: bytes, purpose: str) -> str:
    sig=parse(sidecar,'signature')
    if sig['purpose']!=purpose or sig['digest']!='sha256:'+sha(payload):
        raise InvalidSet('Signature purpose or digest mismatch')
    encoded=sig['signature']
    try:
        raw=base64.urlsafe_b64decode(encoded+'==')
        if len(raw)!=64 or base64.urlsafe_b64encode(raw).decode().rstrip('=')!=encoded:
            raise InvalidSet('Noncanonical signature encoding')
        message=f'slime/{purpose}/1'.encode('ascii')+b'\x00'+hashlib.sha256(payload).digest()
        Ed25519PublicKey.from_public_bytes(key_decode(sig['signer'])).verify(raw,message)
    except InvalidSet:
        raise
    except Exception as exc:
        raise InvalidSet('Invalid Ed25519 signature') from exc
    return sig['signer']

def verify_set(directory: Path, expected_signer: str|None=None):
    directory=directory.resolve(strict=True)
    if not directory.is_dir():
        raise InvalidSet('Expected a staged directory')
    actual={}
    collisions=set()
    for item in directory.rglob('*'):
        if item.is_symlink():
            raise InvalidSet('Links not supported')
        name=item.relative_to(directory).as_posix()
        safe_path(name)
        folded=name.lower()
        if folded in collisions:
            raise InvalidSet('Case-insensitive path collision')
        collisions.add(folded)
        if item.is_file():
            actual[name]=item
        elif not item.is_dir():
            raise InvalidSet('Nonregular filesystem entry')
    if 'set.json' not in actual:
        raise InvalidSet('This checker requires an optional inventory; plain sets need no such file')
    inv_bytes=actual['set.json'].read_bytes()
    inventory=parse(inv_bytes,'set')
    names=[x['path'] for x in inventory['files']]
    if names!=sorted(names) or len(names)!=len(set(names)):
        raise InvalidSet('Inventory paths must be unique and sorted')
    if set(names)!=(set(actual)-CONTROL):
        raise InvalidSet('Missing or extra inventory files')
    signer=None
    if 'set.sig.json' in actual:
        signer=verify_signature(inv_bytes,actual['set.sig.json'].read_bytes(),'set')
    if expected_signer is not None and signer!=expected_signer:
        raise InvalidSet('Unexpected or missing publisher signature')
    versions={}
    origin_bodies={}
    payload={}
    for entry in inventory['files']:
        name=entry['path'];safe_path(name)
        raw=actual[name].read_bytes()
        if len(raw)!=entry['bytes'] or sha(raw)!=entry['sha256']:
            raise InvalidSet('Member mismatch: '+name)
        payload[name]=raw
        origin=entry.get('origin')
        if origin:
            if name.startswith('records/'):
                parts=name.split('/')
                if len(parts)>=4 and len(parts[1])==52:
                    key_decode(parts[1])
                    conventional='pubky://'+parts[1]+'/'+ '/'.join(parts[2:])
                    if conventional!=origin:
                        raise InvalidSet('Path and origin mapping disagree')
            versions[(origin,entry['sha256'])]=raw
            origin_bodies.setdefault(origin,set()).add(entry['sha256'])
    statements={}
    for name,item in actual.items():
        if name.startswith('proofs/') and name.endswith('.json') and not name.endswith('.sig.json'):
            # This example checker recognizes only its own explicit record proof prefix.
            raw=item.read_bytes()
            try:
                probe=json.loads(raw)
            except Exception:
                continue
            if not isinstance(probe,dict) or probe.get('format')!='slime-record/1':
                continue
            statement=parse(raw,'record')
            side_name=name[:-5]+'.sig.json'
            if side_name not in actual:
                raise InvalidSet('Missing statement signature')
            author=verify_signature(raw,actual[side_name].read_bytes(),'record')
            if author!=origin_author(statement['origin']):
                raise InvalidSet('Statement signer is not record author')
            if statement['operation']=='put' and (statement['origin'],statement['content_sha256']) not in versions:
                raise InvalidSet('Missing/mismatched authenticated body in this complete fixture')
            statements['sha256:'+sha(raw)]=statement
    # Same-origin references are checked when the referenced statement is available.
    for sid,statement in statements.items():
        for parent in statement['parents']:
            if parent in statements and statements[parent]['origin']!=statement['origin']:
                raise InvalidSet('Cross-origin parent')
            if parent==sid:
                raise InvalidSet('Self-parent cycle')
    return {'id':'sha256:'+sha(inv_bytes),'signer':signer,'files':len(names),'versions':versions,
            'statements':statements,'payload':payload,'previous':inventory.get('previous')}

def merge_heads(results):
    """Fixture-only projection of verified same-origin statements; not mixed-source policy."""
    statements={}
    for result in results:
        statements.update(result['statements'])
    referenced=set()
    for sid,statement in statements.items():
        for parent in statement['parents']:
            if parent in statements:
                if statements[parent]['origin']!=statement['origin']:
                    raise InvalidSet('Cross-origin parent across imports')
                referenced.add(parent)
    heads={}
    for sid,statement in statements.items():
        if sid not in referenced:
            heads.setdefault(statement['origin'],[]).append((sid,statement['operation']))
    return {k:sorted(v) for k,v in sorted(heads.items())}

# Record adapter for the synthetic pub/slime-example/ namespace. A real client uses the
# adapters for the deployed Pubky App and shop schemas; the derived fields are the same.

def derive(origin: str, raw: bytes) -> dict:
    """Derive an entry's kind, refs, and label from the original bytes."""
    author=origin_author(origin)
    path=urlsplit(origin).path
    if not path.startswith(EXAMPLE):
        return {'kind':'other'}
    rest=path[len(EXAMPLE):]
    if rest.startswith('blobs/'):
        if rest[len('blobs/'):]!=sha(raw):
            raise InvalidSet('Blob name does not match its bytes')
        return {'kind':'blob'}
    body=load_json(raw)
    if not isinstance(body,dict):
        raise InvalidSet('Record body is not an object')
    if rest.startswith('tags/'):
        label,target=body.get('label'),body.get('uri')
        if not isinstance(label,str) or not re.fullmatch(r'[^\s]{1,100}',label) or not isinstance(target,str):
            raise InvalidSet('Tag needs a label and a target')
        return {'kind':'tag','label':label,'refs':[target]}
    media=body.get('media',[])
    if not isinstance(media,list) or not all(isinstance(m,str) for m in media):
        raise InvalidSet('media must be a list of URIs')
    if rest.startswith('listings/'):
        return {'kind':'listing','refs':sorted({f'pubky://{author}{EXAMPLE}shop.json',*media})}
    if rest=='shop.json':
        return {'kind':'shop','refs':sorted(set(media))} if media else {'kind':'shop'}
    return {'kind':'other'}

def dependencies(origin: str, raw: bytes) -> list[str]:
    """Records this record needs in order to render: targets, shops, media."""
    return [r for r in derive(origin,raw).get('refs',[]) if r.startswith('pubky://') and '/pub/' in r]

def same_claims(claimed: dict, derived: dict) -> None:
    for field in ('kind','refs','label'):
        if claimed.get(field)!=derived.get(field):
            raise InvalidSet(f'Entry {field} does not match the record bytes: '+claimed['uri'])

def matches(query: dict, uri: str, fields: dict) -> bool:
    """The four deterministic primitives. fields carries kind, refs, and label."""
    kind=query.get('kind')
    if kind is not None and fields['kind']!=kind:
        return False
    op=query['op']
    refs=fields.get('refs',[])
    if op=='author':
        return authority(uri)==query['key']
    if op=='label':
        return fields['kind']=='tag' and fields.get('label')==query['label']
    if op=='refs':
        return query['uri'] in refs
    if op=='domain':
        return any(host_of(r)==query['host'] for r in refs)
    raise InvalidSet('Unsupported query: '+op)

def entry_in_scope(entry: dict, scopes: list) -> bool:
    refs=entry.get('refs',[])
    keys={authority(entry['uri'])}|{authority(r) for r in refs if r.startswith('pubky://')}
    for scope in scopes:
        if 'key' in scope and scope['key'] in keys:
            return True
        if 'label' in scope and entry['kind']=='tag' and entry.get('label')==scope['label']:
            return True
        if 'host' in scope and any(host_of(r)==scope['host'] for r in refs):
            return True
    return False

def check_entries(entries: list) -> int:
    """Entries are in strictly ascending seq order, with sorted refs and no repeated version."""
    last=-1
    versions=set()
    for entry in entries:
        number=int(entry['seq'])
        if number<=last:
            raise InvalidSet('Entries must be in strictly ascending seq order')
        last=number
        authority(entry['uri'])
        refs=entry.get('refs')
        if refs is not None and refs!=sorted(refs):
            raise InvalidSet('Entry refs must be sorted')
        if 'sha256' in entry:
            version=(entry['uri'],entry['sha256'])
            if version in versions:
                raise InvalidSet('Repeated entry version')
            versions.add(version)
    return last

def check_provider(ad: dict, now: datetime|None=None) -> None:
    roles=set(ad['roles'])
    if roles&LIVE_ROLES and not ad.get('endpoints'):
        raise InvalidSet('A provider with records, query, or notices roles needs an endpoint')
    if ('slices' in roles)!=bool(ad.get('slices')):
        raise InvalidSet('Listed slices and the slices role must agree')
    issued,expires=timestamp(ad['issued_at']),timestamp(ad['expires_at'])
    if expires<=issued:
        raise InvalidSet('Advertisement expires before it is issued')
    if now is not None and not issued<=now<expires:
        raise InvalidSet('Advertisement is not valid at this time')
    if ad['provider'] in ad.get('peers',[]):
        raise InvalidSet('An advertisement must not list its own provider as a peer')

def verify_provider(advertisement: bytes, sidecar: bytes, now: datetime|None=None) -> dict:
    signer=verify_signature(advertisement,sidecar,'provider')
    ad=parse(advertisement,'provider')
    if signer!=ad['provider']:
        raise InvalidSet('Advertisement is not signed by the provider it describes')
    check_provider(ad,now)
    return ad

def providers_for(advertisements: list, key: str, role: str, now: datetime) -> list:
    """Verified advertisements that serve a role for a key, newest sequence per provider."""
    best={}
    for ad in advertisements:
        check_provider(ad,now)
        if role in ad['roles'] and {'key':key} in ad['scopes']:
            current=best.get(ad['provider'])
            if current is None or ad['sequence']>current['sequence']:
                best[ad['provider']]=ad
    return [best[k] for k in sorted(best)]

def check_slice(entries_doc: dict, versions: dict) -> int:
    last=check_entries(entries_doc['entries'])
    if int(entries_doc['through'])<last:
        raise InvalidSet('Slice through is below its highest entry')
    listed=set()
    for entry in entries_doc['entries']:
        if not entry.get('gone') and not entry_in_scope(entry,entries_doc['scopes']):
            raise InvalidSet('Entry outside the slice scope: '+entry['uri'])
        if 'sha256' in entry:
            listed.add((entry['uri'],entry['sha256']))
            raw=versions.get((entry['uri'],entry['sha256']))
            if raw is not None:
                same_claims(entry,derive(entry['uri'],raw))
    for version in versions:
        if version not in listed:
            raise InvalidSet('Record body without a slice entry: '+version[0])
    return last

def verify_slice(directory: Path, expected_provider: str|None=None):
    result=verify_set(directory)
    if 'slice.json' not in result['payload']:
        raise InvalidSet('A slice needs slice.json')
    entries_doc=parse(result['payload']['slice.json'],'slice')
    if result['signer'] is None or result['signer']!=entries_doc['provider']:
        raise InvalidSet('A slice must be signed by its provider key')
    if expected_provider is not None and entries_doc['provider']!=expected_provider:
        raise InvalidSet('Unexpected slice provider')
    check_slice(entries_doc,result['versions'])
    result['slice']=entries_doc
    return result

def verify_candidates(data: bytes, advertisement: dict|None=None) -> dict:
    response=parse(data,'candidates')
    entries=response['entries']
    check_entries(entries)
    query=response['query']
    if 'after' in query and entries and int(entries[0]['seq'])<=int(query['after']):
        raise InvalidSet('Entry at or before the after cursor')
    for entry in entries:
        if not entry.get('gone') and not matches(query,entry['uri'],entry):
            raise InvalidSet('Entry does not match the query: '+entry['uri'])
    if not response['complete'] and (not entries or response['next']!=entries[-1]['seq']):
        raise InvalidSet('next must be the seq of the last returned entry')
    if advertisement is not None:
        if response['provider']!=advertisement['provider']:
            raise InvalidSet('Response is from a different provider')
        if 'query' not in advertisement['roles']:
            raise InvalidSet('Provider does not advertise the query role')
        limit=advertisement.get('limits',{}).get('max_entries')
        if limit is not None and len(entries)>limit:
            raise InvalidSet('Response exceeds the advertised entry limit')
        for entry in entries:
            if not entry.get('gone') and not entry_in_scope(entry,advertisement['scopes']):
                raise InvalidSet('Entry outside the advertised scope: '+entry['uri'])
    return response

def verify_notice(data: bytes, source_uri: str, source: bytes) -> dict:
    notice=parse(data,'notice')
    if notice['source']!=source_uri:
        raise InvalidSet('Fetched record is not the notice source')
    if 'sha256' in notice and sha(source)!=notice['sha256']:
        raise InvalidSet('Source bytes do not match the notice')
    target=notice['target']
    refs=derive(source_uri,source).get('refs',[])
    bare_key=urlsplit(target).path=='/'
    if not (target in refs or (bare_key and any(r.startswith('pubky://') and authority(r)==authority(target) for r in refs))):
        raise InvalidSet('Source record does not reference the notice target')
    return notice

def parse_txt(value: str) -> dict:
    """Parse a _slime TXT value: space-separated key=value pairs starting with v=slime1."""
    try:
        encoded=value.encode('ascii')
    except UnicodeEncodeError as exc:
        raise InvalidSet('TXT value must be ASCII') from exc
    if len(encoded)>255:
        raise InvalidSet('TXT value exceeds one 255-byte string')
    tokens=value.split(' ')
    if tokens[0]!='v=slime1':
        raise InvalidSet('TXT value must start with v=slime1')
    fields={}
    for token in tokens:
        key,sep,val=token.partition('=')
        if not sep or not re.fullmatch(r'[a-z]+',key) or not val:
            raise InvalidSet('Malformed TXT field: '+token)
        if key in fields:
            raise InvalidSet('Duplicate TXT field: '+key)
        fields[key]=val
    return fields

def resolve_home(identity: str, route: bytes, identity_txt: str, failover_key: str|None=None,
                 failover_txt: str|None=None, now: datetime|None=None, last_seq: int|None=None) -> dict:
    """Pick the homeserver to read and publish through, from PKARR TXT values and a route.

    identity_txt comes from the identity key's PKARR packet and failover_txt from the
    failover key's packet. PKARR verifies each packet's signature; this checks Slime's rules.
    """
    pin=parse_txt(identity_txt).get('rt')
    if pin is None or pin!=sha(route):
        raise InvalidSet('Route does not match the PKARR pin')
    doc=parse(route,'route')
    if doc['identity']!=identity:
        raise InvalidSet('Route belongs to a different identity')
    if failover_txt is None:
        return {'home':doc['homeservers'][0],'via':'route'}
    failover=doc.get('failover')
    if failover is None:
        raise InvalidSet('Route names no failover key')
    if failover_key!=failover['key']:
        raise InvalidSet('Failover record comes from a key the route does not name')
    fields=parse_txt(failover_txt)
    if fields.get('id')!=identity:
        raise InvalidSet('Failover record names a different identity')
    if fields.get('rt')!=pin:
        raise InvalidSet('Failover record refers to a different route')
    home=fields.get('home')
    if home not in doc['homeservers']:
        raise InvalidSet('Failover target is not an enrolled homeserver')
    seq=fields.get('seq','')
    if not re.fullmatch(r'0|[1-9][0-9]{0,18}',seq):
        raise InvalidSet('Failover seq must be a decimal integer')
    if now is None or now>=timestamp(failover['expires_at']):
        raise InvalidSet('Failover authority expired')
    if last_seq is not None and int(seq)<=last_seq:
        raise InvalidSet('Stale failover record')
    return {'home':home,'via':'failover','seq':int(seq)}

class LocalIndex:
    """Fixture-scale replica index. Admits checked bytes and answers the four primitives."""
    def __init__(self):
        self._items={}

    def __len__(self):
        return len(self._items)

    def admit(self, uri: str, raw: bytes, expected_sha256: str|None=None, claimed: dict|None=None) -> bool:
        digest=sha(raw)
        if expected_sha256 is not None and digest!=expected_sha256:
            raise InvalidSet('Supplied bytes do not match the expected hash')
        derived=derive(uri,raw)
        if claimed is not None:
            same_claims(claimed,derived)
        added=(uri,digest) not in self._items
        self._items[(uri,digest)]=(raw,derived)
        return added

    def admit_set(self, result: dict) -> int:
        entries={(e['uri'],e['sha256']):e for e in result.get('slice',{}).get('entries',[]) if 'sha256' in e}
        return sum(self.admit(o,raw,d,entries.get((o,d))) for (o,d),raw in sorted(result['versions'].items()))

    def query(self, op: str, **args) -> list[str]:
        query={'op':op,**args}
        return sorted({uri for (uri,_),(_,fields) in self._items.items() if matches(query,uri,fields)})

    def dependencies(self, uri: str) -> list[tuple[str,str]]:
        retained={u for (u,_) in self._items}
        needed=set()
        for (u,_),(raw,_) in self._items.items():
            if u==uri:
                needed.update(dependencies(u,raw))
        return [(d,'retained' if d in retained else 'missing') for d in sorted(needed)]

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--expected-signer')
    args=parser.parse_args()
    try:
        if (args.directory/'provider.json').is_file():
            ad=verify_provider((args.directory/'provider.json').read_bytes(),(args.directory/'provider.sig.json').read_bytes())
            print(json.dumps({'provider':ad['provider'],'sequence':ad['sequence'],'roles':ad['roles'],'scopes':len(ad['scopes'])},indent=2))
            return 0
        if (args.directory/'slice.json').is_file():
            result=verify_slice(args.directory,args.expected_signer)
            print(json.dumps({'id':result['id'],'provider':result['signer'],'files':result['files'],
                              'entries':len(result['slice']['entries']),'through':result['slice']['through']},indent=2))
            return 0
        result=verify_set(args.directory,args.expected_signer)
        print(json.dumps({k:v for k,v in result.items() if k in {'id','signer','files'}},indent=2))
        return 0
    except (InvalidSet,OSError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
