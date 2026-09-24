#!/usr/bin/env python3
"""Read-only checker for the PROPOSED optional Slime fixture formats.

Validates staged directories, not hostile archives. No network, extraction, signing,
or credential access. This is not a production importer or a complete Pubky client.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
ALPHABET = 'ybndrfg8ejkmcpqxot1uwisza345h769'
CONTROL = {'set.json', 'set.sig.json'}
LIMITS = {'set': 16*1024*1024, 'signature': 8192, 'record': 65536, 'observation': 65536}

class InvalidSet(ValueError):
    """Invalid, unsupported, incomplete, or over-budget fixture."""

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

def parse(data: bytes, kind: str):
    if len(data) > LIMITS[kind] or data.startswith(b'\xef\xbb\xbf'):
        raise InvalidSet('Control-file size limit or UTF-8 BOM')
    try:
        result = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=reject_constant)
        schema = json.loads((ROOT/'schemas'/f'{kind}.schema.json').read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
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
    for entry in inventory['files']:
        name=entry['path'];safe_path(name)
        raw=actual[name].read_bytes()
        if len(raw)!=entry['bytes'] or sha(raw)!=entry['sha256']:
            raise InvalidSet('Member mismatch: '+name)
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
    return {'id':'sha256:'+sha(inv_bytes),'signer':signer,'files':len(names),'versions':versions,'statements':statements}

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

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--expected-signer')
    args=parser.parse_args()
    try:
        result=verify_set(args.directory,args.expected_signer)
        print(json.dumps({k:v for k,v in result.items() if k not in {'versions','statements'}},indent=2))
        return 0
    except (InvalidSet,OSError) as exc:
        print(str(exc),file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
