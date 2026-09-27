#!/usr/bin/env python3
"""Generate every Slime reference fixture in this directory and rewrite expected.json.

Usage, from the repository root: python examples/make_fixtures.py

Records are real pubky.app records: tag ids are pubky-app-specs HashIds (BLAKE3, first 16 bytes,
Crockford base32), post and file ids are TimestampIds, blobs are named by the HashId of their bytes,
and a post reaches its image through a file record whose src is the blob. Every author has an app
key holding a Pubky grant (`pubky-grant` JWS, encoded as pubky-common encodes them) with write on
/pub/pubky.app/, and that key signs each record at write time: the author signature. Bob's slice
key, an indexer's answer key, and Alice's failover key hold grants for /pub/slime/ or /pub/. Every key
is derived from a fixed, public seed, so rerunning reproduces every fixture byte for byte. These are
test keys only: anyone can derive them, and no real identity uses them.
"""
from __future__ import annotations
import hashlib
import json
import shutil
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

EXAMPLES = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLES))
from check_sets import b3, b64url, crockford, derive, hash_id, key_encode  # noqa: E402

APP = 'pub/pubky.app'
FIXTURE_DIRS = ['github-inventoried', 'github-signed', 'shops-public', 'shops-events', 'expired-grant', 'headline']
ISSUED, EXPIRES = 1790078400, 1853150400  # 2026-09-22 12:00 and 2028-09-21 12:00 UTC
BASE = 1790164800000000  # 2026-09-23T12:00:00Z in microseconds
OLD_ISSUED, OLD_EXPIRES = 1740830400, 1756728000  # 2025-03-01 12:00 and 2025-09-01 12:00 UTC
OLD_POST = 1743508800000000  # 2025-04-01T12:00:00Z in microseconds

def dump(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True)+'\n').encode()

def compact(obj) -> bytes:
    """pubky.app records as the app writes them: compact JSON in struct field order."""
    return json.dumps(obj, separators=(',', ':')).encode()

def seed(name: str) -> bytes:
    return hashlib.sha256(b'slime reference fixture: '+name.encode()).digest()

def new_key(name: str):
    secret = Ed25519PrivateKey.from_private_bytes(seed(name))
    return secret, key_encode(secret.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))

def jws(secret, kid: str, typ: str, payload: bytes) -> bytes:
    header = b64url(json.dumps({'alg': 'EdDSA', 'kid': kid, 'typ': typ}, separators=(',', ':'), sort_keys=True).encode())
    signature = secret.sign((header+'.'+b64url(payload)).encode('ascii'))
    return (header+'..'+b64url(signature)+'\n').encode()

def grant(secret, issuer: str, client_id: str, caps: list, client_key: str, issued=ISSUED, expires=EXPIRES) -> str:
    header = b64url(json.dumps({'alg': 'EdDSA', 'typ': 'pubky-grant'}, separators=(',', ':')).encode())
    jti = b64url(seed(f'grant {issuer} {client_key} {issued}')[:16])
    claims = b64url(compact({'iss': issuer, 'client_id': client_id, 'caps': caps, 'cnf': client_key,
                             'jti': jti, 'iat': issued, 'exp': expires}))
    return header+'.'+claims+'.'+b64url(secret.sign((header+'.'+claims).encode('ascii')))

class Author:
    """An identity whose app key signs its records at write time."""
    def __init__(self, name: str, client_id='franky.pubky.app', caps=('/pub/pubky.app/:rw',)):
        self.secret, self.key = new_key(name)
        self.app_secret, self.app_key = new_key(name+' app')
        self.grant = grant(self.secret, self.key, client_id, list(caps), self.app_key)

    def sign(self, uri: str, raw: bytes, iat: int, app=None) -> str:
        app_secret, app_key = app or (self.app_secret, self.app_key)
        header = b64url(json.dumps({'alg': 'EdDSA', 'kid': app_key, 'typ': 'pubky-record'}, separators=(',', ':'), sort_keys=True).encode())
        claims = b64url(compact({'uri': uri, 'content_hash': b3(raw), 'iat': iat}))
        return header+'.'+claims+'.'+b64url(app_secret.sign((header+'.'+claims).encode('ascii')))

def timestamp_id(micros: int) -> str:
    return crockford(micros.to_bytes(8, 'big'))

def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)

def record_path(uri: str) -> str:
    return 'records/'+uri[len('pubky://'):]

def write_folder(folder: Path, files: dict, created_at: str, signer=None, previous: str|None=None) -> str:
    """files maps relative path to (bytes, None) or (bytes, (origin, sig, grant))."""
    for name, (data, _) in files.items():
        write(folder/name, data)
    inventory = {'created_at': created_at, 'format': 'slime-set/1', 'files': []}
    for name in sorted(files):
        data, record = files[name]
        entry = {'blake3': b3(data), 'bytes': len(data), 'path': name}
        if record:
            entry['origin'], entry['sig'], entry['grant'] = record
        inventory['files'].append(entry)
    if previous:
        inventory['previous'] = previous
    raw = dump(inventory)
    write(folder/'set.json', raw)
    if signer:
        write(folder/'set.jws', jws(signer[0], signer[1], 'slime-set', raw))
    return b3(raw)

def main() -> None:
    for name in FIXTURE_DIRS:
        if (EXAMPLES/name).exists():
            shutil.rmtree(EXAMPLES/name)
    exporter_secret, exporter = new_key('exporter')
    author, dana, curator, carol, mallory = (Author(n) for n in ('author', 'dana', 'curator', 'carol', 'mallory'))
    bob_secret, bob = new_key('bob')
    publisher_secret, bob_publisher = new_key('bob slice')
    bob_grant = grant(bob_secret, bob, 'slices.bob.example', ['/pub/slime/:rw'], bob_publisher)
    indexer_operator_secret, indexer_operator = new_key('indexer operator')
    answer_secret, indexer = new_key('indexer')
    indexer_grant = grant(indexer_operator_secret, indexer_operator, 'index.example', ['/pub/slime/:rw'], indexer)
    alice_secret, alice = new_key('alice')
    failover_secret, alice_failover = new_key('alice failover')
    alice_grant = grant(alice_secret, alice, 'publisher.alice.example', ['/pub/:rw'], alice_failover)
    read_only_grant = grant(alice_secret, alice, 'reader.alice.example', ['/pub/slime/:r'], alice_failover)
    _, hs_primary = new_key('homeserver primary')
    _, hs_alternate = new_key('homeserver alternate')
    _, hs_unenrolled = new_key('homeserver unenrolled')
    _, mirror = new_key('mirror')
    signed = {}

    def record(who: Author, rest: str, raw: bytes, iat: int):
        uri = f'pubky://{who.key}/{APP}/{rest}'
        signed[uri] = (raw, who.sign(uri, raw, iat), who.grant)
        return uri

    def files_for(*uris):
        return {record_path(u): (signed[u][0], (u, signed[u][1], signed[u][2])) for u in uris}

    # A GitHub tag by one author, with the author's profile.
    tag_target, tag_label = 'https://github.com/pubky/pubky-homeserver', 'rust'
    author_tag = record(author, 'tags/'+hash_id(f'{tag_target}:{tag_label}'.encode()),
                        compact({'uri': tag_target, 'label': tag_label, 'created_at': BASE}), ISSUED+86400)
    author_profile = record(author, 'profile.json', compact({'name': 'Tag Author', 'bio': 'Synthetic fixture account.', 'image': None,
                            'links': [{'title': 'GitHub', 'url': 'https://github.com/pubky'}], 'status': None}), ISSUED+86400)
    github = files_for(author_tag, author_profile)
    github['keys.txt'] = ((author.key+'\n').encode(), None)
    github['links.txt'] = ((tag_target+'\n').encode(), None)
    about = ("Synthetic folder: one pubky.app tag on a GitHub repository and its author's profile, each with its author "
             "signature. The tag id is the pubky-app-specs HashId of `uri:label`. This folder is a selection, not a backup.")
    github['README.md'] = (("# GitHub reference, unsigned inventory\n\n"+about+" `set.json` lists every file with its hash, "
                            "and no exporter signs it.\n").encode(), None)
    inventoried = write_folder(EXAMPLES/'github-inventoried', github, '2026-09-23T13:00:00Z')
    github['README.md'] = (("# GitHub reference, signed inventory\n\n"+about+" An exporter signs `set.json` in "
                            "`set.jws`.\n").encode(), None)
    signed_set = write_folder(EXAMPLES/'github-signed', github, '2026-09-23T13:00:00Z', (exporter_secret, exporter))

    # Dana's shop as ordinary pubky.app records, each signed by Dana's app key.
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="#222"/></svg>\n'
    iat = ISSUED+86400
    blob = record(dana, 'blobs/'+hash_id(svg), svg, iat)
    file_uri = record(dana, 'files/'+timestamp_id(BASE+1_000_000), compact({'name': 'harbor.svg', 'created_at': BASE+1_000_000,
                      'src': blob, 'content_type': 'image/svg+xml', 'size': len(svg)}), iat)
    listing_rest = 'posts/'+timestamp_id(BASE+2_000_000)
    listing_raw = compact({'content': 'Harbor print, A3. 30 USD, local pickup. Details: https://dana-prints.example/harbor.',
                           'kind': 'image', 'parent': None, 'embed': None, 'attachments': [file_uri]})
    listing = record(dana, listing_rest, listing_raw, iat)
    withdrawn_raw = compact({'content': 'Harbor print, A3. Sold out and withdrawn.',
                             'kind': 'image', 'parent': None, 'embed': None, 'attachments': [file_uri]})
    withdrawn_sig = dana.sign(listing, withdrawn_raw, iat+3600)
    shirt = record(dana, 'posts/'+timestamp_id(BASE+3_000_000), compact({'content': 'Independent print shirt, size L, 50 USD.',
                   'kind': 'short', 'parent': None, 'embed': None, 'attachments': None}), iat)
    dana_profile = record(dana, 'profile.json', compact({'name': 'Dana Prints', 'bio': 'Synthetic seller fixture.', 'image': None,
                          'links': [{'title': 'Shop', 'url': 'https://dana-prints.example'}], 'status': None}), iat)
    curator_tag = record(curator, 'tags/'+hash_id(f'{listing}:local-print'.encode()),
                         compact({'uri': listing, 'label': 'local-print', 'created_at': BASE+4_000_000}), iat)
    shop = files_for(dana_profile, blob, file_uri, listing, shirt, curator_tag)
    shop['keys.txt'] = ((dana.key+'\n'+curator.key+'\n').encode(), None)
    shop['links.txt'] = ((listing+'\n').encode(), None)
    shop['README.md'] = (("# Dana's shop\n\nSynthetic public catalog as ordinary pubky.app records: Dana's profile, two posts "
                          "used as listings, the image post's file record and its blob, and a curator's tag. Every record "
                          "carries its author signature. An exporter signs the selection. No order, buyer, address, invoice, "
                          "or payment destination is included. A copy reserves nothing.\n").encode(), None)
    shops = write_folder(EXAMPLES/'shops-public', shop, '2026-09-23T13:00:00Z', (exporter_secret, exporter))

    # Dana's homeserver event stream: the listing is edited to withdrawn, and the shirt post deleted.
    events = [('PUT', dana_profile), ('PUT', blob), ('PUT', file_uri), ('PUT', listing), ('PUT', shirt),
              ('PUT', listing, withdrawn_raw), ('DEL', shirt)]
    lines = []
    for cursor, event in enumerate(events, start=101):
        op, u = event[0], event[1]
        raw = event[2] if len(event) > 2 else signed[u][0]
        lines.append(f'event: {op}\ndata: {u}\ndata: cursor: {cursor}' + (f'\ndata: content_hash: {b3(raw)}' if op == 'PUT' else ''))
    folder = EXAMPLES/'shops-events'
    write(folder/'events.txt', ('\n\n'.join(lines)+'\n').encode())
    write(folder/record_path(listing), withdrawn_raw)
    write(folder/'withdrawn.sig', (withdrawn_sig+'\n').encode())
    write(folder/'README.md', ("# Dana's event stream\n\n`events.txt` is Dana's homeserver `/events-stream` output in its SSE "
                               "format. The listing post is edited to withdrawn at cursor 106 and the shirt post is deleted at "
                               "cursor 107. `records/` holds the withdrawn version of the listing, and `withdrawn.sig` is Dana's "
                               "author signature over it, made an hour after the first version.\n").encode())

    # A record that outlives its grant: signed while an older grant was valid, and a copy signed after it expired.
    old_app = new_key('dana old app')
    old_grant = grant(dana.secret, dana.key, 'franky.pubky.app', ['/pub/pubky.app/:rw'], old_app[1], OLD_ISSUED, OLD_EXPIRES)
    old_raw = compact({'content': 'Spring print sale, all A4 prints 15 USD.', 'kind': 'short', 'parent': None,
                       'embed': None, 'attachments': None})
    old_post = f'pubky://{dana.key}/{APP}/posts/'+timestamp_id(OLD_POST)
    folder = EXAMPLES/'expired-grant'
    write(folder/'record.json', old_raw)
    write(folder/'grant.jws', (old_grant+'\n').encode())
    write(folder/'record.sig', (dana.sign(old_post, old_raw, OLD_POST//1_000_000, old_app)+'\n').encode())
    write(folder/'late.sig', (dana.sign(old_post, old_raw, OLD_EXPIRES+86400, old_app)+'\n').encode())
    write(folder/'README.md', ("# A record that outlives its grant\n\nA post Dana wrote in April 2025 with an app key whose "
                               "grant ran from March to September 2025. `record.sig` was made while the grant was valid, so it "
                               "still verifies after the grant expired. `late.sig` claims a signing time after the grant "
                               "expired, so a reader rejects it.\n").encode())

    # Headline: Bob publishes a static slice of Dana's key; an indexer answers signed queries.
    head = EXAMPLES/'headline'
    carol_tag = record(carol, 'tags/'+hash_id(f'{listing}:great-print'.encode()),
                       compact({'uri': listing, 'label': 'great-print', 'created_at': BASE+170_000_000_000}), iat+86400)

    def entry(seq, u):
        raw, sig, g = signed[u]
        return {'blake3': b3(raw), 'grant': g, 'seq': str(seq), 'sig': sig, 'uri': u, **derive(u, raw)}
    entries = [entry(i, u) for i, u in enumerate([dana_profile, blob, file_uri, listing, shirt, curator_tag], start=1)]
    carol_entry = entry(7, carol_tag)
    scopes = [{'key': dana.key}]

    def slice_files(slice_entries, through, as_of, text):
        files = {'README.md': (text.encode(), None)}
        files['slice.json'] = (dump({'as_of': as_of, 'entries': slice_entries, 'format': 'slime-slice/1', 'grant': bob_grant,
                                     'publisher': bob_publisher, 'scopes': scopes, 'through': through}), None)
        files.update(files_for(*[e['uri'] for e in slice_entries]))
        return files
    slice1 = write_folder(head/'bob-slice-1', slice_files(entries, '6', '2026-09-25T09:00:00Z',
        "# Bob's slice of Dana's shop, first snapshot\n\nBob chose to share Dana's key. This is the published result, a "
        "static export signed by Bob's slice key, whose Pubky grant travels in `slice.json`. Every record carries Dana's or "
        "the curator's author signature, so a reader checks each copy against its author, not against Bob.\n"),
        '2026-09-25T09:00:00Z', (publisher_secret, bob_publisher))
    slice2 = write_folder(head/'bob-slice-2', slice_files(entries+[carol_entry], '7', '2026-09-25T11:00:00Z',
        "# Bob's slice of Dana's shop, second snapshot\n\nThe same choice one refresh later, with Carol's tag on the image "
        "post. `set.json` names the first snapshot as `previous`.\n"),
        '2026-09-25T11:00:00Z', (publisher_secret, bob_publisher), previous=slice1)

    def answer(name, query, answer_entries, as_of):
        body = dump({'as_of': as_of, 'complete': True, 'entries': answer_entries, 'format': 'slime-candidates/1',
                     'grant': indexer_grant, 'indexer': indexer, 'operator': indexer_operator, 'query': query})
        write(head/'indexer-answers'/f'{name}.json', body)
        write(head/'indexer-answers'/f'{name}.jws', jws(answer_secret, indexer, 'slime-answer', body))
    answer('author-dana', {'key': dana.key, 'op': 'author'}, [e for e in entries if e['uri'].startswith(f'pubky://{dana.key}/')], '2026-09-25T09:30:00Z')
    answer('label-great-print', {'label': 'great-print', 'op': 'label'}, [carol_entry], '2026-09-25T11:30:00Z')
    write(head/'indexer-answers/README.md', (
        "# Signed answers from an indexer\n\nAn indexer that Synonym does not run answers two queries: `author` for Dana's key, "
        "and `label` for great-print, which finds Carol's tag. Each answer is signed by the indexer's key, whose Pubky grant "
        "from the indexer's operator travels in the answer. Each entry carries its record's author signature. `complete` is the "
        "indexer's claim.\n").encode())

    forged_raw = compact({'content': 'Harbor print, A3. 300 USD, pay first: https://pay.mallory.example.',
                          'kind': 'image', 'parent': None, 'embed': None, 'attachments': [file_uri]})
    write(head/'forged-listing/record.json', forged_raw)
    write(head/'forged-listing/record.sig', (mallory.sign(listing, forged_raw, iat)+'\n').encode())
    write(head/'forged-listing/grant.jws', (mallory.grant+'\n').encode())
    write(head/'forged-listing/README.md', (
        "# A forged listing\n\nA copy of Dana's image post with a different price and payment link, offered under Dana's URI. "
        "Mallory signed it with the app key of her own valid grant. A reader rejects it: the grant was not issued by Dana.\n").encode())

    services = dump({'format': 'slime-services/1', 'identity': alice, 'issued_at': '2026-09-20T12:00:00Z',
                     'mirrors': [mirror], 'sequence': 1})
    write(head/'alice-home/services.json', services)

    def home(target, with_grant=alice_grant):
        return dump({'format': 'slime-home/1', 'grant': with_grant, 'home': target, 'identity': alice,
                     'issued_at': '2026-09-25T12:00:00Z', 'sequence': 1})
    for name, body, secret, kid in [('home', home(hs_alternate), failover_secret, alice_failover),
                                    ('rejected/unenrolled-home', home(hs_unenrolled), failover_secret, alice_failover),
                                    ('rejected/wrong-signer-home', home(hs_alternate), publisher_secret, bob_publisher),
                                    ('rejected/read-only-grant-home', home(hs_alternate, read_only_grant), failover_secret, alice_failover)]:
        write(head/'alice-home'/f'{name}.json', body)
        write(head/'alice-home'/f'{name}.jws', jws(secret, kid, 'slime-home', body))
    write(head/'alice-home/README.md', (
        "# Alice's services and home statement\n\n`services.json` names Alice's mirror, which republishes her PKARR packet and "
        "carries her home statement. `home.json` is what her failover key signs after her primary homeserver refused her writes "
        "while still serving stale reads. It names her alternate as the homeserver that decides her edits, and it carries the "
        "Pubky grant whose client key signed it. A reader accepts `home` only if it is one of the `_pubky` records in Alice's "
        "PKARR packet. The tests pass those targets as the PKARR library would resolve them: primary, then alternate.\n\n"
        "`rejected/` holds three statements a reader must ignore: one names a homeserver outside her `_pubky` records, one is "
        "signed by a key that is not the grant's client key, and one carries a grant that can only read `/pub/slime/`.\n").encode())
    write(head/'README.md', (
        "# Headline fixtures\n\nThe files for the Alice, Bob, Carol, and Dana acceptance test. Dana's records are the pubky.app "
        "records from `shops-public/`. `test_headline.py` runs the test's data path offline against these files.\n\n"
        "| Path | What it holds |\n|---|---|\n"
        "| `bob-slice-1/` | Bob's static slice of Dana's key |\n"
        "| `bob-slice-2/` | The next snapshot, with Carol's tag |\n"
        "| `indexer-answers/` | Two signed answers from an indexer Synonym does not run |\n"
        "| `forged-listing/` | A forged copy of Dana's listing, signed under someone else's grant |\n"
        "| `alice-home/` | Alice's services document, her home statement, and three statements to reject |\n").encode())

    expected = {
        'identities': {'exporter': exporter, 'author': author.key, 'dana': dana.key, 'dana_app': dana.app_key,
                       'curator': curator.key, 'carol': carol.key, 'mallory': mallory.key, 'bob': bob,
                       'bob_publisher': bob_publisher, 'indexer': indexer, 'indexer_operator': indexer_operator,
                       'alice': alice, 'alice_failover': alice_failover, 'homeserver_primary': hs_primary,
                       'homeserver_alternate': hs_alternate, 'homeserver_unenrolled': hs_unenrolled, 'mirror': mirror},
        'uris': {'author_tag': author_tag, 'author_profile': author_profile, 'dana_profile': dana_profile,
                 'blob': blob, 'file': file_uri, 'listing': listing, 'shirt': shirt, 'curator_tag': curator_tag,
                 'carol_tag': carol_tag, 'old_post': old_post},
        'hashes': {'listing': b3(listing_raw), 'listing_withdrawn': b3(withdrawn_raw), 'shirt': b3(signed[shirt][0]),
                   'forged': b3(forged_raw), 'old_post': b3(old_raw)},
        'sets': {'github-inventoried': inventoried, 'github-signed': signed_set, 'shops-public': shops,
                 'headline/bob-slice-1': slice1, 'headline/bob-slice-2': slice2},
    }
    write(EXAMPLES/'expected.json', dump(expected))

if __name__ == '__main__':
    main()
