#!/usr/bin/env python3
"""Read-only checker for the Slime fixture formats.

Checks staged folders and slices, author signatures on records, signed indexer answers,
services documents, home statements, and merges over homeserver event streams. No network,
extraction, signing, or credential access. This is not a production importer or a complete
Pubky client.

Hashes are BLAKE3 in standard base64, the encoding the homeserver uses for its ETag and for
content_hash in its event stream. Signatures are detached JWS (RFC 7515 Appendix F) with EdDSA.
Every Slime signing key is the client key of a Pubky grant: a `pubky-grant` JWS the identity
key signs through Ring, binding a client key (`cnf`) to capabilities and an expiry. An author's
app key signs each record at write time; that record signature is the author signature. The
record-signature encoding here is provisional until pubky-homeserver settles its delegated-key
design; what a reader checks (issuer, client key, capabilities, signing time) is not.
"""
from __future__ import annotations
import argparse
import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from blake3 import blake3
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
ALPHABET = 'ybndrfg8ejkmcpqxot1uwisza345h769'
CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
CONTROL = {'set.json', 'set.jws'}
LIMITS = {'set': 16*1024*1024, 'jws': 8192, 'slice': 16*1024*1024, 'candidates': 4*1024*1024,
          'services': 65536, 'home': 16384}
APP = '/pub/pubky.app/'
SLIME_PATH = '/pub/slime/'
MAX_REFS = 64
TAG_LABEL_MAX = 20
TAG_INVALID = set(',: \t\n\r')
OCT_2024_MICROS = 1727740800000000
PUBKY_REF = re.compile(r'pubky://([ybndrfg8ejkmcpqxot1uwisza345h769]{52})(/pub/[^\s?#]+|/)?')
WEB_REF = re.compile(r'https?://[^\s]+')
TEXT_URL = re.compile(r'https?://[^\s<>"\'()\[\]{}]+')
TEXT_PUBKY = re.compile(r'pubky://[ybndrfg8ejkmcpqxot1uwisza345h769]{52}(?:/pub/[^\s<>"\'()\[\]{}?#]+)?')
GRANT_TYP = 'pubky-grant'
RECORD_TYP = 'pubky-record'

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

def b3(data: bytes) -> str:
    """BLAKE3 in standard base64, as the homeserver's ETag and event content_hash."""
    return base64.b64encode(blake3(data).digest()).decode()

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip('=')

def b64url_decode(segment: str) -> bytes:
    if not re.fullmatch(r'[A-Za-z0-9_-]*',segment):
        raise InvalidSet('Invalid base64url segment')
    return base64.urlsafe_b64decode(segment+'='*(-len(segment)%4))

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
    if len(data) > LIMITS[kind]:
        raise InvalidSet('Control-file size limit')
    result = load_json(data)
    try:
        schema = json.loads((ROOT/'schemas'/f'{kind}.schema.json').read_text())
        Draft202012Validator(schema, registry=REGISTRY, format_checker=FormatChecker()).validate(result)
    except Exception as exc:
        raise InvalidSet(f'Invalid {kind} JSON: {exc}') from exc
    return result

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

def crockford(data: bytes) -> str:
    """Crockford base32 without padding, as the `base32` crate used by pubky-app-specs."""
    bits=''.join(f'{b:08b}' for b in data)
    bits+='0'*(-len(bits)%5)
    return ''.join(CROCKFORD[int(bits[i:i+5],2)] for i in range(0,len(bits),5))

def hash_id(data: bytes) -> str:
    """pubky-app-specs HashId: first 16 bytes of BLAKE3, Crockford base32."""
    return crockford(blake3(data).digest()[:16])

def timestamp_id_micros(text: str) -> int:
    """Decode a pubky-app-specs TimestampId: 13 Crockford characters over 8 big-endian bytes."""
    if len(text)!=13 or any(c not in CROCKFORD for c in text):
        raise InvalidSet('Invalid timestamp id: '+text)
    n=0
    for c in text:
        n=(n<<5)|CROCKFORD.index(c)
    if n & 1:
        raise InvalidSet('Noncanonical timestamp id')
    micros=n>>1
    if micros<OCT_2024_MICROS:
        raise InvalidSet('Timestamp id before October 2024')
    return micros

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

# Detached JWS (RFC 7515 Appendix F): header..signature over base64url(header).base64url(bytes).

def verify_jws(payload: bytes, compact: str, typ: str) -> str:
    """Verify a detached EdDSA JWS over exact bytes. Returns the signer key from `kid`."""
    if len(compact.encode())>LIMITS['jws']:
        raise InvalidSet('Signature file too large')
    parts=compact.strip().split('.')
    if len(parts)!=3 or parts[1]!='':
        raise InvalidSet('A signature is a detached JWS: header..signature')
    header=load_json(b64url_decode(parts[0]))
    if not isinstance(header,dict) or set(header)!={'alg','kid','typ'}:
        raise InvalidSet('Signature header must carry exactly alg, kid, and typ')
    if header['alg']!='EdDSA' or header['typ']!=typ:
        raise InvalidSet('Signature type mismatch: expected '+typ)
    signature=b64url_decode(parts[2])
    if len(signature)!=64 or b64url(signature)!=parts[2]:
        raise InvalidSet('Noncanonical signature encoding')
    try:
        Ed25519PublicKey.from_public_bytes(key_decode(header['kid'])).verify(signature,(parts[0]+'.'+b64url(payload)).encode('ascii'))
    except Exception as exc:
        raise InvalidSet('Invalid Ed25519 signature') from exc
    return header['kid']

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
    if 'set.jws' in actual:
        signer=verify_jws(inv_bytes,actual['set.jws'].read_text(),'slime-set')
    if expected_signer is not None and signer!=expected_signer:
        raise InvalidSet('Unexpected or missing exporter signature')
    versions={}
    sigs={}
    payload={}
    for entry in inventory['files']:
        name=entry['path']
        raw=actual[name].read_bytes()
        if len(raw)!=entry['bytes'] or b3(raw)!=entry['blake3']:
            raise InvalidSet('Member mismatch: '+name)
        payload[name]=raw
        origin=entry.get('origin')
        if origin:
            parts=name.split('/')
            if parts[0]!='records' or len(parts)<4:
                raise InvalidSet('Origins apply to records/ only')
            if 'pubky://'+'/'.join(parts[1:])!=origin:
                raise InvalidSet('Path and origin mapping disagree')
            if 'sig' not in entry or 'grant' not in entry:
                raise InvalidSet('A record needs its author signature: '+origin)
            verify_record_signature(origin,entry['blake3'],entry['sig'],entry['grant'])
            versions[(origin,entry['blake3'])]=raw
            sigs[(origin,entry['blake3'])]=(entry['sig'],entry['grant'])
    return {'id':b3(inv_bytes),'signer':signer,'files':len(names),'versions':versions,'sigs':sigs,
            'payload':payload,'previous':inventory.get('previous')}

# Entry derivation. Record types from pubky-app-specs get their adapter; every other record is
# kind "other", indexed by URI, author, and the pubky:// and http(s) URIs in its JSON body.

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
            add_ref(found,value)
    walk(body)
    return sorted(found)[:MAX_REFS]

def add_ref(found: set, value: str) -> None:
    match=PUBKY_REF.fullmatch(value)
    if match:
        try:
            key_decode(match.group(1))
        except InvalidSet:
            return
        found.add('pubky://'+match.group(1)+(match.group(2) or '/'))
    elif WEB_REF.fullmatch(value):
        found.add(value)

def text_refs(text: str) -> set:
    """Links in free text: http(s) URLs and pubky:// URIs, with trailing punctuation removed."""
    found=set()
    for pattern in (TEXT_URL,TEXT_PUBKY):
        for match in pattern.findall(text):
            add_ref(found,match.rstrip('.,;:!?'))
    return found

def app_body(raw: bytes) -> dict:
    body=load_json(raw)
    if not isinstance(body,dict):
        raise InvalidSet('pubky.app record body is not an object')
    return body

def tag_fields(body: dict) -> tuple[str,str]:
    label,target=body.get('label'),body.get('uri')
    if not isinstance(label,str) or not isinstance(target,str) or not isinstance(body.get('created_at'),int):
        raise InvalidSet('Tag needs uri, label, and created_at')
    if label!=label.strip().lower() or not 1<=len(label)<=TAG_LABEL_MAX or TAG_INVALID&set(label):
        raise InvalidSet('Tag label breaks pubky-app-specs rules: '+label)
    return label,target

def derive(origin: str, raw: bytes) -> dict:
    """Derive an entry's kind, refs, and label from the original bytes."""
    author=origin_author(origin)
    path=urlsplit(origin).path
    if path.startswith(APP):
        return derive_app(author,path[len(APP):],raw)
    try:
        body=load_json(raw)
    except InvalidSet:
        return {'kind':'other'}
    refs=extract_refs(body)
    return {'kind':'other','refs':refs} if refs else {'kind':'other'}

def derive_app(author: str, rest: str, raw: bytes) -> dict:
    segment,_,ident=rest.partition('/')
    if rest=='profile.json':
        body=app_body(raw)
        found=set()
        if isinstance(body.get('image'),str):
            add_ref(found,body['image'])
        for link in body.get('links') or []:
            if isinstance(link,dict) and isinstance(link.get('url'),str):
                add_ref(found,link['url'])
        return with_refs('profile',found)
    if rest=='last_read':
        return {'kind':'last_read'}
    if segment=='blobs':
        if ident!=hash_id(raw):
            raise InvalidSet('Blob id does not match its bytes')
        return {'kind':'blob'}
    if segment=='tags':
        body=app_body(raw)
        label,target=tag_fields(body)
        if ident!=hash_id(f'{target}:{label}'.encode()):
            raise InvalidSet('Tag id does not match uri and label')
        return {'kind':'tag','label':label,'refs':[target]}
    if segment=='bookmarks':
        body=app_body(raw)
        if not isinstance(body.get('uri'),str) or ident!=hash_id(body['uri'].encode()):
            raise InvalidSet('Bookmark id does not match its uri')
        return {'kind':'bookmark','refs':[body['uri']]}
    if segment in {'follows','mutes'}:
        key_decode(ident)
        return {'kind':segment[:-1],'refs':[f'pubky://{ident}/']}
    if segment=='files':
        timestamp_id_micros(ident)
        body=app_body(raw)
        if not isinstance(body.get('src'),str):
            raise InvalidSet('File needs a src')
        return with_refs('file',{body['src']})
    if segment=='posts':
        timestamp_id_micros(ident)
        body=app_body(raw)
        found=text_refs(body.get('content','')) if isinstance(body.get('content'),str) else set()
        if isinstance(body.get('parent'),str):
            found.add(body['parent'])
        embed=body.get('embed')
        if isinstance(embed,dict) and isinstance(embed.get('uri'),str):
            found.add(embed['uri'])
        found.update(a for a in body.get('attachments') or [] if isinstance(a,str))
        return with_refs('post',found)
    if segment=='feeds':
        app_body(raw)
        return {'kind':'feed'}
    return with_refs('other',set(extract_refs(load_json(raw))))

def with_refs(kind: str, found: set) -> dict:
    refs=sorted(found)[:MAX_REFS]
    return {'kind':kind,'refs':refs} if refs else {'kind':kind}

def profile_uri(key: str) -> str:
    return f'pubky://{key}{APP}profile.json'

def dependencies(origin: str, raw: bytes) -> list[str]:
    """What a record needs to render: referenced records, and its author's profile."""
    derived=derive(origin,raw)
    needed={r for r in derived.get('refs',[]) if r.startswith('pubky://') and '/pub/' in r}
    if derived['kind']!='profile':
        needed.add(profile_uri(origin_author(origin)))
    return sorted(needed)

def same_claims(claimed: dict, derived: dict) -> None:
    for field in ('kind','refs','label'):
        if claimed.get(field)!=derived.get(field):
            raise InvalidSet(f'Entry {field} does not match the record bytes: '+claimed['uri'])

def is_last_read(uri: str) -> bool:
    return urlsplit(uri).path==APP+'last_read'

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
        if is_last_read(entry['uri']):
            raise InvalidSet('The last-read marker is never shared')
        refs=entry.get('refs')
        if refs is not None and refs!=sorted(refs):
            raise InvalidSet('Entry refs must be sorted')
        if 'blake3' in entry:
            version=(entry['uri'],entry['blake3'])
            if version in versions:
                raise InvalidSet('Repeated entry version')
            versions.add(version)
    return last

# Pubky grants: pubky-grant JWS, EdDSA over header.payload by the iss key (pubky-common).

def verify_grant(compact: str, now: datetime) -> dict:
    parts=compact.split('.')
    if len(parts)!=3:
        raise InvalidSet('A grant is a three-part JWS')
    header=load_json(b64url_decode(parts[0]))
    claims=load_json(b64url_decode(parts[1]))
    if not isinstance(header,dict) or header.get('alg')!='EdDSA' or header.get('typ')!=GRANT_TYP:
        raise InvalidSet('A grant header must be alg EdDSA and typ pubky-grant')
    if not isinstance(claims,dict) or not {'iss','client_id','caps','cnf','jti','iat','exp'}<=set(claims):
        raise InvalidSet('Grant claims are incomplete')
    if not isinstance(claims['caps'],list) or not all(isinstance(c,str) for c in claims['caps']):
        raise InvalidSet('Grant caps must be a list of capability strings')
    if not isinstance(claims['exp'],int) or not isinstance(claims['iat'],int):
        raise InvalidSet('Grant iat and exp must be integers')
    signature=b64url_decode(parts[2])
    if len(signature)!=64 or b64url(signature)!=parts[2]:
        raise InvalidSet('Noncanonical grant signature encoding')
    try:
        Ed25519PublicKey.from_public_bytes(key_decode(claims['iss'])).verify(signature,(parts[0]+'.'+parts[1]).encode('ascii'))
    except InvalidSet:
        raise
    except Exception as exc:
        raise InvalidSet('Invalid grant signature') from exc
    key_decode(claims['cnf'])
    if now.timestamp()>=claims['exp']:
        raise InvalidSet('Grant has expired')
    return claims

def grant_allows_write(claims: dict, path: str) -> bool:
    """True when a grant capability `<scope>:<actions>` covers path with the w action."""
    for capability in claims['caps']:
        scope,sep,actions=capability.rpartition(':')
        if sep and scope.startswith('/') and actions and 'w' in actions and set(actions)<={'r','w'} and path.startswith(scope):
            return True
    return False

def check_grant_key(grant: str, issuer: str, key: str, now: datetime) -> dict:
    """The key is the grant's client key, the identity issued it, and it may write Slime paths."""
    claims=verify_grant(grant,now)
    if claims['iss']!=issuer:
        raise InvalidSet('Grant was issued by a different identity')
    if claims['cnf']!=key:
        raise InvalidSet("Signing key is not the grant's client key")
    if not grant_allows_write(claims,SLIME_PATH):
        raise InvalidSet('Grant does not allow writing '+SLIME_PATH)
    return claims

def verify_record_signature(uri: str, content_hash: str, sig: str, grant: str) -> dict:
    """An author signature: a JWS over {uri, content_hash, iat} by the client key of a grant the
    author issued, whose capabilities allow writing the record's path, made while the grant was
    valid. A record outlives its grant: the signature stays valid after exp."""
    parts=sig.split('.')
    if len(parts)!=3 or not parts[1]:
        raise InvalidSet('A record signature is a JWS with an attached payload')
    header=load_json(b64url_decode(parts[0]))
    claims=load_json(b64url_decode(parts[1]))
    if not isinstance(header,dict) or set(header)!={'alg','kid','typ'} or header['alg']!='EdDSA' or header['typ']!=RECORD_TYP:
        raise InvalidSet('A record signature header must be alg EdDSA, kid, and typ pubky-record')
    if not isinstance(claims,dict) or set(claims)!={'uri','content_hash','iat'} or not isinstance(claims['iat'],int):
        raise InvalidSet('A record signature carries exactly uri, content_hash, and iat')
    if claims['uri']!=uri or claims['content_hash']!=content_hash:
        raise InvalidSet('Record signature is for other bytes or another URI')
    signature=b64url_decode(parts[2])
    if len(signature)!=64 or b64url(signature)!=parts[2]:
        raise InvalidSet('Noncanonical record signature encoding')
    try:
        Ed25519PublicKey.from_public_bytes(key_decode(header['kid'])).verify(signature,(parts[0]+'.'+parts[1]).encode('ascii'))
    except InvalidSet:
        raise
    except Exception as exc:
        raise InvalidSet('Invalid record signature') from exc
    at=datetime.fromtimestamp(claims['iat'],timezone.utc)
    grant_claims=verify_grant(grant,at)
    if not grant_claims['iat']<=claims['iat']:
        raise InvalidSet('Record signed before its grant was issued')
    if grant_claims['iss']!=origin_author(uri):
        raise InvalidSet("Record signature grant was not issued by the record's author")
    if grant_claims['cnf']!=header['kid']:
        raise InvalidSet("Record signed by a key that is not the grant's client key")
    if not grant_allows_write(grant_claims,urlsplit(uri).path):
        raise InvalidSet("Grant does not allow writing the record's path")
    return claims

def check_signed_entries(entries: list) -> None:
    for entry in entries:
        if not entry.get('gone'):
            verify_record_signature(entry['uri'],entry['blake3'],entry['sig'],entry['grant'])

def check_slice(entries_doc: dict, versions: dict) -> int:
    last=check_entries(entries_doc['entries'])
    if int(entries_doc['through'])<last:
        raise InvalidSet('Slice through is below its highest entry')
    listed=set()
    for entry in entries_doc['entries']:
        if not entry.get('gone') and not entry_in_scope(entry,entries_doc['scopes']):
            raise InvalidSet('Entry outside the shared scopes: '+entry['uri'])
        if 'blake3' in entry:
            listed.add((entry['uri'],entry['blake3']))
            raw=versions.get((entry['uri'],entry['blake3']))
            if raw is not None:
                same_claims(entry,derive(entry['uri'],raw))
    check_signed_entries(entries_doc['entries'])
    for version in versions:
        if is_last_read(version[0]):
            raise InvalidSet('The last-read marker is never shared')
        if version not in listed:
            raise InvalidSet('Record body without a slice entry: '+version[0])
    return last

def verify_slice(directory: Path, expected_publisher: str|None=None, now: datetime|None=None):
    """A static signed export. Without a time, the publisher's grant is checked as of as_of."""
    result=verify_set(directory)
    if 'slice.json' not in result['payload']:
        raise InvalidSet('A slice needs slice.json')
    entries_doc=parse(result['payload']['slice.json'],'slice')
    if result['signer'] is None or result['signer']!=entries_doc['publisher']:
        raise InvalidSet('A slice must be signed by its publisher key')
    if expected_publisher is not None and entries_doc['publisher']!=expected_publisher:
        raise InvalidSet('Unexpected slice publisher')
    at=now or timestamp(entries_doc['as_of'])
    claims=verify_grant(entries_doc['grant'],at)
    check_grant_key(entries_doc['grant'],claims['iss'],entries_doc['publisher'],at)
    check_slice(entries_doc,result['versions'])
    result['operator']=claims['iss']
    result['slice']=entries_doc
    return result

def verify_answer(data: bytes, signature: str, operator: str|None=None, now: datetime|None=None) -> dict:
    """A signed indexer answer: candidates for one query, each carrying its author signature,
    signed by the indexer's grant key. `complete` stays the indexer's claim."""
    signer=verify_jws(data,signature,'slime-answer')
    answer=parse(data,'candidates')
    if signer!=answer['indexer']:
        raise InvalidSet('Answer is not signed by the indexer it names')
    if operator is not None and answer['operator']!=operator:
        raise InvalidSet('Answer is from an indexer operator the reader did not configure')
    check_grant_key(answer['grant'],answer['operator'],answer['indexer'],now or timestamp(answer['as_of']))
    entries=answer['entries']
    check_entries(entries)
    query=answer['query']
    if 'after' in query and entries and int(entries[0]['seq'])<=int(query['after']):
        raise InvalidSet('Entry at or before the after cursor')
    for entry in entries:
        if not entry.get('gone') and not matches(query,entry['uri'],entry):
            raise InvalidSet('Entry does not match the query: '+entry['uri'])
    if not answer['complete'] and (not entries or answer['next']!=entries[-1]['seq']):
        raise InvalidSet('next must be the seq of the last returned entry')
    check_signed_entries(entries)
    return answer

# Services documents, home statements, and failover.

def load_services(data: bytes, identity: str) -> dict:
    """A services document names the identity's mirrors and is published through its own session."""
    doc=parse(data,'services')
    if doc['identity']!=identity:
        raise InvalidSet('Services document belongs to a different identity')
    return doc

def verify_home(home: bytes, signature: str, identity: str, homeservers: list, now: datetime,
                last_sequence: int|None=None) -> dict:
    """homeservers are the `_pubky` targets of the identity's PKARR packet, in priority order."""
    signer=verify_jws(home,signature,'slime-home')
    statement=parse(home,'home')
    if statement['identity']!=identity:
        raise InvalidSet('Home statement names a different identity')
    check_grant_key(statement['grant'],identity,signer,now)
    if statement['home'] not in homeservers:
        raise InvalidSet("Home statement names a homeserver outside the identity's _pubky records")
    if last_sequence is not None and statement['sequence']<=last_sequence:
        raise InvalidSet('Stale home statement')
    return statement

def resolve_home(identity: str, homeservers: list, homes: list, now: datetime) -> dict:
    """The homeserver that decides mutable paths: the newest valid home statement, else the
    first `_pubky` target. homes are (bytes, signature) pairs from any carrier."""
    if not homeservers:
        raise InvalidSet('The identity publishes no homeserver')
    best=None
    for home,signature in homes:
        try:
            statement=verify_home(home,signature,identity,homeservers,now)
        except InvalidSet:
            continue
        rank=(statement['sequence'],-homeservers.index(statement['home']))
        if best is None or rank>best[0]:
            best=(rank,statement)
    if best is not None:
        return {'home':best[1]['home'],'via':'home statement','sequence':best[1]['sequence']}
    return {'home':homeservers[0],'via':'pkarr'}

# Merge over homeserver event streams (the /events-stream SSE format).

def parse_events(text: str) -> list:
    events=[]
    for block in text.strip().split('\n\n'):
        lines=[line for line in block.strip().split('\n') if line]
        if not lines[0].startswith('event: '):
            raise InvalidSet('Event block must start with event:')
        op=lines[0][len('event: '):]
        data=[line[len('data: '):] for line in lines[1:] if line.startswith('data: ')]
        if op not in {'PUT','DEL'} or len(data)!=len(lines)-1 or not data:
            raise InvalidSet('Malformed event block')
        fields=dict(item.split(': ',1) for item in data[1:])
        event={'op':op,'uri':data[0],'cursor':int(fields['cursor'])}
        if op=='PUT':
            event['blake3']=fields['content_hash']
        events.append(event)
    cursors=[e['cursor'] for e in events]
    if cursors!=sorted(cursors) or len(set(cursors))!=len(cursors):
        raise InvalidSet('Event cursors must increase')
    return events

def log_state(events: list) -> dict:
    state={}
    for event in events:
        state[event['uri']]=('put',event['blake3']) if event['op']=='PUT' else ('del',)
    return state

def current_versions(logs: dict, copies: dict, authority_home: str|None=None) -> dict:
    """Heads per URI. logs maps an enrolled homeserver to its events; copies maps a URI to the
    BLAKE3 hashes of author-signed copies held from suppliers (unsigned copies never get here). A log decides over copies; the home statement's
    homeserver decides between logs; disagreement without a decider keeps every head."""
    states={home:log_state(events) for home,events in logs.items()}
    heads={}
    for uri in sorted({u for s in states.values() for u in s}|set(copies)):
        seen={home:s[uri] for home,s in states.items() if uri in s}
        if authority_home in seen:
            heads[uri]=[seen[authority_home]]
        elif seen:
            heads[uri]=sorted(set(seen.values()))
        else:
            heads[uri]=sorted(('put',h) for h in set(copies[uri]))
    return heads

class LocalIndex:
    """Fixture-scale replica index. Admits checked bytes and answers the four primitives."""
    def __init__(self):
        self._items={}

    def __len__(self):
        return len(self._items)

    def admit(self, uri: str, raw: bytes, sig: str|None=None, grant: str|None=None,
              claimed: dict|None=None, from_origin: bool=False) -> bool:
        """Copies need a valid author signature. Bytes read from the author's own homeserver
        (from_origin) carry the homeserver session's authority instead."""
        digest=b3(raw)
        if claimed is not None and claimed.get('blake3') not in (None,digest):
            raise InvalidSet('Supplied bytes do not match the expected hash')
        if not from_origin:
            if sig is None or grant is None:
                raise InvalidSet('A copy without an author signature is rejected')
            verify_record_signature(uri,digest,sig,grant)
        derived=derive(uri,raw)
        if claimed is not None:
            same_claims(claimed,derived)
        added=(uri,digest) not in self._items
        self._items[(uri,digest)]=(raw,derived)
        return added

    def admit_set(self, result: dict) -> int:
        entries={(e['uri'],e['blake3']):e for e in result.get('slice',{}).get('entries',[]) if 'blake3' in e}
        return sum(self.admit(o,raw,*result['sigs'][(o,d)],entries.get((o,d)))
                   for (o,d),raw in sorted(result['versions'].items()))

    def query(self, op: str, **args) -> list[str]:
        query={'op':op,**args}
        return sorted({uri for (uri,_),(_,fields) in self._items.items() if matches(query,uri,fields)})

    def state(self, uri: str, holders: set, withheld: set) -> str:
        if uri in withheld:
            return 'withheld'
        if any(u==uri for (u,_) in self._items):
            return 'retained'
        return 'fetchable' if uri in holders else 'missing'

    def dependencies(self, uri: str, holders: set=frozenset(), withheld: set=frozenset()) -> list[tuple[str,str]]:
        needed=set()
        for (u,_),(raw,_) in self._items.items():
            if u==uri:
                needed.update(dependencies(u,raw))
        return [(d,self.state(d,holders,withheld)) for d in sorted(needed)]

    def closure(self, uri: str, holders: set=frozenset(), withheld: set=frozenset()) -> list[tuple[str,str]]:
        """Every transitive dependency, such as post to file to blob, with its state."""
        seen={}
        frontier=[uri]
        while frontier:
            for dep,state in self.dependencies(frontier.pop(),holders,withheld):
                if dep not in seen and dep!=uri:
                    seen[dep]=state
                    if state=='retained':
                        frontier.append(dep)
        return sorted(seen.items())

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--expected-signer')
    args=parser.parse_args()
    try:
        if (args.directory/'slice.json').is_file():
            result=verify_slice(args.directory,args.expected_signer)
            print(json.dumps({'id':result['id'],'publisher':result['signer'],'files':result['files'],
                              'entries':len(result['slice']['entries']),'through':result['slice']['through']},indent=2))
            return 0
        result=verify_set(args.directory,args.expected_signer)
        print(json.dumps({k:v for k,v in result.items() if k in {'id','signer','files'}},indent=2))
        return 0
    except (InvalidSet,OSError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
