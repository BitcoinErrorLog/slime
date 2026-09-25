#!/usr/bin/env python3
"""Read-only checker for the Slime fixture formats.

Checks staged folders and slices, provider advertisements, query responses,
notices, routes, and home statements. No network, extraction, signing, or credential
access. This is not a production importer or a complete Pubky client.

Key delegation follows Pubky Unified Key Delegation (UKD): an identity's RootKey, held
in Ring, signs a KeyBinding and AppCerts that delegate AppKeys. Verifying the KeyBinding
and AppCerts is the UKD library's job. Functions here take the verified app_keys entries
it returns and check Slime's rules on top of them.
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
          'notice': 8192, 'route': 65536, 'home': 8192}
EXAMPLE = '/pub/slime-example/'
LIVE_ROLES = {'records', 'query', 'notices'}
MAX_REFS = 64
PUBKY_REF = re.compile(r'pubky://([ybndrfg8ejkmcpqxot1uwisza345h769]{52})(/pub/[^\s?#]+|/)?')
WEB_REF = re.compile(r'https?://[^\s]+')

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

# Entries are derived from original bytes. A real client has an adapter for each record type
# pubky-app-specs defines. In this fixture namespace, tags/ use the pubky-app-specs tag shape
# (uri, label, created_at) and blobs/ are named by their SHA-256. Every other record is kind
# "other": Slime retains, shares, and indexes it without knowing its schema, and takes its refs
# from the pubky:// and http(s) URIs found anywhere in its JSON body.

def extract_refs(body) -> list[str]:
    found=set()
    def walk(value):
        if isinstance(value,dict):
            for item in value.values():
                walk(item)
        elif isinstance(value,list):
            for item in value:
                walk(item)
        elif isinstance(value,str) and len(value)<=8192:
            match=PUBKY_REF.fullmatch(value)
            if match:
                try:
                    key_decode(match.group(1))
                except InvalidSet:
                    return
                found.add('pubky://'+match.group(1)+(match.group(2) or '/'))
            elif WEB_REF.fullmatch(value):
                found.add(value)
    walk(body)
    return sorted(found)[:MAX_REFS]

def derive(origin: str, raw: bytes) -> dict:
    """Derive an entry's kind, refs, and label from the original bytes."""
    origin_author(origin)
    path=urlsplit(origin).path
    rest=path[len(EXAMPLE):] if path.startswith(EXAMPLE) else None
    if rest is not None and rest.startswith('blobs/'):
        if rest[len('blobs/'):]!=sha(raw):
            raise InvalidSet('Blob name does not match its bytes')
        return {'kind':'blob'}
    if rest is not None and rest.startswith('tags/'):
        body=load_json(raw)
        label,target=(body.get('label'),body.get('uri')) if isinstance(body,dict) else (None,None)
        if not isinstance(label,str) or not re.fullmatch(r'[^\s]{1,100}',label) or not isinstance(target,str):
            raise InvalidSet('Tag needs a label and a target')
        return {'kind':'tag','label':label,'refs':[target]}
    try:
        body=load_json(raw)
    except InvalidSet:
        return {'kind':'other'}
    refs=extract_refs(body)
    return {'kind':'other','refs':refs} if refs else {'kind':'other'}

def dependencies(origin: str, raw: bytes) -> list[str]:
    """Records this record needs in order to render: targets, media, parents."""
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
    """Scopes are the published form of sharing choices: a key, a label, a host, or one record."""
    refs=entry.get('refs',[])
    keys={authority(entry['uri'])}|{authority(r) for r in refs if r.startswith('pubky://')}
    for scope in scopes:
        kinds=scope.get('kinds')
        if kinds is not None and entry['kind'] not in kinds:
            continue
        if 'key' in scope and scope['key'] in keys:
            return True
        if 'label' in scope and entry['kind']=='tag' and entry.get('label')==scope['label']:
            return True
        if 'host' in scope and any(host_of(r)==scope['host'] for r in refs):
            return True
        if 'uri' in scope and (entry['uri']==scope['uri'] or scope['uri'] in refs):
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

def check_delegation(delegation: dict, identity: str, key: str, cert_id: str, now: datetime) -> None:
    """Check that an identity currently delegates a key for Slime.

    delegation is the identity's verified KeyBinding for app_id "slime", reduced to what the
    UKD library returns after checking the KeyBinding and each AppCert against the RootKey:
    {"identity": ..., "app_id": "slime", "app_keys": [{"key", "cert_id", "expires_at"?}]}.
    """
    key_decode(key)
    if not re.fullmatch(r'[0-9a-f]{32}',cert_id):
        raise InvalidSet('Malformed cert_id')
    if delegation.get('identity')!=identity or delegation.get('app_id')!='slime':
        raise InvalidSet('No slime KeyBinding for this identity')
    for entry in delegation.get('app_keys',[]):
        if entry.get('key')==key and entry.get('cert_id')==cert_id:
            expires=entry.get('expires_at')
            if expires is not None and now>=timestamp(expires):
                raise InvalidSet('Delegated key has expired')
            return
    raise InvalidSet('Key is not delegated by this identity')

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
    if ad['provider']==ad['operator']:
        raise InvalidSet('A provider key must be delegated, not the operator identity key')
    if any(peer['provider']==ad['provider'] for peer in ad.get('peers',[])):
        raise InvalidSet('An advertisement must not list its own provider as a peer')

def verify_provider(advertisement: bytes, sidecar: bytes, delegation: dict|None=None,
                    now: datetime|None=None) -> dict:
    signer=verify_signature(advertisement,sidecar,'provider')
    ad=parse(advertisement,'provider')
    if signer!=ad['provider']:
        raise InvalidSet('Advertisement is not signed by the provider it describes')
    check_provider(ad,now)
    if delegation is not None:
        if now is None:
            raise InvalidSet('Checking a delegation needs the current time')
        check_delegation(delegation,ad['operator'],ad['provider'],ad['cert_id'],now)
    return ad

def providers_for(advertisements: list, key: str, role: str, now: datetime) -> list:
    """Verified advertisements that serve a role for a key, newest sequence per provider."""
    best={}
    for ad in advertisements:
        check_provider(ad,now)
        if role in ad['roles'] and any(scope.get('key')==key for scope in ad['scopes']):
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
            raise InvalidSet('Entry outside the shared scopes: '+entry['uri'])
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

def accepts_notice(notice: dict, provider: str, route: dict|None, advertisement: dict|None) -> bool:
    """A provider accepts a notice for key X when X's route lists it as a notice provider, or
    when its own advertised scopes already cover X or the target record."""
    target_key=authority(notice['target'])
    if route is not None and route['identity']==target_key and any(p['provider']==provider for p in route.get('notice',[])):
        return True
    if advertisement is not None and advertisement['provider']==provider and 'notices' in advertisement['roles']:
        return any(scope.get('key')==target_key or scope.get('uri')==notice['target'] for scope in advertisement['scopes'])
    return False

def verify_route(route: bytes, sidecar: bytes, identity: str) -> dict:
    """A route is signed by the identity's RootKey, through Ring's typed signing."""
    signer=verify_signature(route,sidecar,'route')
    doc=parse(route,'route')
    if signer!=identity or doc['identity']!=identity:
        raise InvalidSet('A route must be signed by its own identity key')
    return doc

def verify_home(home: bytes, sidecar: bytes, identity: str, route: bytes, route_sidecar: bytes,
                delegation: dict, now: datetime, last_sequence: int|None=None) -> dict:
    """A home statement is signed by the failover AppKey the route names and UKD delegates."""
    signer=verify_signature(home,sidecar,'home')
    statement=parse(home,'home')
    if statement['identity']!=identity:
        raise InvalidSet('Home statement names a different identity')
    if statement['route']!='sha256:'+sha(route):
        raise InvalidSet('Home statement names a different route')
    doc=verify_route(route,route_sidecar,identity)
    if doc.get('failover')!=signer:
        raise InvalidSet("Home statement is not signed by the route's failover key")
    check_delegation(delegation,identity,signer,statement['cert_id'],now)
    if statement['home'] not in doc['homeservers']:
        raise InvalidSet('Home statement names a homeserver the route does not enroll')
    if last_sequence is not None and statement['sequence']<=last_sequence:
        raise InvalidSet('Stale home statement')
    return statement

def resolve_home(identity: str, routes: list, homes: list, delegation: dict, now: datetime) -> dict:
    """Pick the homeserver to read and publish through.

    routes and homes are (bytes, signature bytes) pairs gathered from any carrier: enrolled
    homeservers, mirrors, peers, folders. Invalid ones are ignored.
    """
    valid={}
    for raw,sig in routes:
        try:
            doc=verify_route(raw,sig,identity)
        except InvalidSet:
            continue
        valid.setdefault(doc['sequence'],{})[raw]=sig
    if not valid:
        raise InvalidSet('No valid route for this identity')
    top=valid[max(valid)]
    if len(top)>1:
        raise InvalidSet('Conflicting routes at the same sequence')
    [(raw,sig)]=top.items()
    doc=parse(raw,'route')
    best=None
    for home,home_sig in homes:
        try:
            statement=verify_home(home,home_sig,identity,raw,sig,delegation,now)
        except InvalidSet:
            continue
        rank=(statement['sequence'],-doc['homeservers'].index(statement['home']))
        if best is None or rank>best[0]:
            best=(rank,statement)
    if best is not None:
        return {'home':best[1]['home'],'via':'failover','sequence':best[1]['sequence']}
    return {'home':doc['homeservers'][0],'via':'route'}

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
            print(json.dumps({'provider':ad['provider'],'operator':ad['operator'],'sequence':ad['sequence'],
                              'roles':ad['roles'],'scopes':len(ad['scopes'])},indent=2))
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
