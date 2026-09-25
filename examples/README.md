# Reference fixtures

Slime has two jobs: P2P indexing, and local fallback when an indexer or homeserver fails. These fixtures cover the file formats both jobs rely on. Public keys and signatures are real. There are no private keys, and no real seller, buyer, or order.

Every record is a real pubky.app record under `/pub/pubky.app/`: profiles, posts, a file record whose `src` is a blob, the blob itself, and tags. Tag ids and blob ids are `pubky-app-specs` HashIds (BLAKE3, first 16 bytes, Crockford base32), and post and file ids are TimestampIds. Every record in these folders passes `pubky-app-specs` 0.8.1 validation.

| Folder | What it covers |
|---|---|
| `github-plain/` | A folder with no inventory: one tag on a GitHub repository and its author's profile |
| `github-inventoried/` | The same folder with an unsigned inventory |
| `github-signed/` | The same folder with an exporter signature |
| `shops-public/` | Dana's shop: profile, two posts used as listings, the image post's file and blob, and a curator's tag, signed by the curator |
| `shops-events/` | Dana's homeserver event stream, in the `/events-stream` SSE format, in which the listing is edited to withdrawn and the second post deleted |
| `headline/` | The Alice, Bob, Carol, and Dana test: Bob's provider advertisement, two snapshots of his slice of Dana's records, two query responses, Carol's notice with proof of work, and Alice's services document and home statements |

Hashes are BLAKE3 in standard base64, the encoding the homeserver uses for its ETag and for `content_hash` in its event stream. Signatures are detached JWS with EdDSA: `header..signature` in a `.jws` file next to the signed file. Provider keys and failover keys are client keys of Pubky grants, `pubky-grant` JWS values encoded exactly as `pubky-common` encodes them, which the checker verifies offline.

Formats and their schemas in [../schemas/](../schemas/):

| Format | Schema |
|---|---|
| `slime-set/1` | `set.schema.json` |
| `slime-provider/1` | `provider.schema.json` |
| `slime-slice/1` | `slice.schema.json` |
| `slime-candidates/1` | `candidates.schema.json` |
| `slime-notice/1` | `notice.schema.json` |
| `slime-services/1` | `services.schema.json` |
| `slime-home/1` | `home.schema.json` |
| Entries, scopes, keys, hashes, and times shared by the above | `common.schema.json` |

## Run the checker

From the repository root, with Python packages `cryptography`, `jsonschema`, and `blake3`:

```sh
python examples/check_sets.py examples/github-signed
python examples/check_sets.py examples/headline/bob-slice-2
python examples/check_sets.py examples/headline/bob-provider
python -m unittest discover -s examples -p 'test_*.py' -v
```

The checker reads staged directories and files. It checks inventories and their signatures, pubky.app record ids and the refs derived from each record, slices against their record bytes and scopes, advertisements and their grants, query responses against the query and the advertised scope, notices against their source record, their acceptance rule, and their proof of work, home statements against grants and `_pubky` targets, and merges over event streams. It does not import `github-plain/`, because that folder is valid sharing without an inventory. It does not extract archives, sign, or use the network.

`test_checks.py` covers folders, signatures, hostile input, pubky.app records, and merges. `test_headline.py` runs the headline test's data path with sockets disabled: provider selection from a held advertisement, slice import, local search over Dana's records, the post-to-file-to-blob dependency chain, Carol's notice, Carol's tag from Bob's answer, and Alice's deciding homeserver from her `_pubky` targets and home statement. It also runs a Sybil flood against the notice queue and fills the requests view. Building the configured mesh from the network is not covered.
