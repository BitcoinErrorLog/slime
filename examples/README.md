# Reference fixtures

Slime has two jobs: replaceable, verifiable indexing, and local fallback when an indexer or homeserver fails. These fixtures cover the file formats both rely on. Public keys and signatures are real. There are no private keys, and no real seller, buyer, or order.

Every record is a real pubky.app record under `/pub/pubky.app/`: profiles, posts, a file record whose `src` is a blob, the blob itself, and tags. Tag ids and blob ids are `pubky-app-specs` HashIds, and post and file ids are TimestampIds. Every record carries its author signature: the author's app key, the client key of a Pubky grant with write on `/pub/pubky.app/`, signs the record's URI, content hash, and signing time. That signature encoding is provisional until `pubky/pubky-homeserver` settles its delegated-key design. What a reader checks is fixed: the grant's issuer is the author, its client key is the signer, its capabilities allow the path, and the signing time falls within the grant's validity.

| Folder | What it covers |
|---|---|
| `github-inventoried/` | One tag on a GitHub repository and its author's profile, with an unsigned inventory |
| `github-signed/` | The same folder with an exporter signature |
| `shops-public/` | Dana's shop: profile, two posts used as listings, the image post's file and blob, and a curator's tag, with an exporter signature |
| `shops-events/` | Dana's homeserver event stream, in the `/events-stream` SSE format, in which the listing is edited to withdrawn and the second post deleted, plus the author signature of the withdrawn version |
| `headline/` | The Alice, Bob, Carol, and Dana test: two snapshots of Bob's static slice of Dana's records, two signed indexer answers, a forged listing signed under someone else's grant, and Alice's services document and home statements |

Hashes are BLAKE3 in standard base64, the encoding the homeserver uses for its ETag and for `content_hash` in its event stream. Signatures on Slime documents are detached JWS with EdDSA: `header..signature` in a `.jws` file next to the signed file. Grants are `pubky-grant` JWS values encoded exactly as `pubky-common` encodes them.

Formats and their schemas in [../schemas/](../schemas/):

| Format | Schema |
|---|---|
| `slime-set/1` | `set.schema.json` |
| `slime-slice/1` | `slice.schema.json` |
| `slime-candidates/1` (signed indexer answer) | `candidates.schema.json` |
| `slime-services/1` | `services.schema.json` |
| `slime-home/1` | `home.schema.json` |
| Entries, scopes, keys, hashes, and times shared by the above | `common.schema.json` |

## Run the checker

From the repository root, with Python packages `cryptography`, `jsonschema`, and `blake3`:

```sh
python examples/check_sets.py examples/github-signed
python examples/check_sets.py examples/headline/bob-slice-2
python -m unittest discover -s examples -p 'test_*.py' -v
```

The checker reads staged directories and files. It checks inventories and their signatures, author signatures on every record, pubky.app record ids and the refs derived from each record, slices against their record bytes and scopes, signed indexer answers, home statements against grants and `_pubky` targets, and merges over event streams. It does not extract archives, sign, or use the network.

`test_checks.py` covers folders, signatures, author signatures, hostile input, pubky.app records, and merges. `test_headline.py` runs the headline test's data path with sockets disabled: Dana's records from a signed indexer answer and Bob's slice, local search, the post-to-file-to-blob dependency chain, a forged listing rejected, Carol's tag found through the indexer's label search, and Alice's deciding homeserver from her `_pubky` targets and home statement. Indexer failover itself needs real clients and is not covered.
