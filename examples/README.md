# Reference fixtures

Slime has two jobs: P2P indexing, and local fallback when an indexer or homeserver fails. These fixtures cover the file formats both jobs rely on. Public keys and Ed25519 signatures are real. There are no private keys, and no real seller, buyer, or order.

| Folder | What it covers |
|---|---|
| `github-plain/` | A folder with no inventory |
| `github-inventoried/` | An unsigned inventory |
| `github-signed/` | An exporter signature |
| `github-history/`, `github-fork/`, `github-joined/` | Deletion, concurrent edits, and a join |
| `shops-public/`, `shops-withdrawn/` | A public catalog and a later withdrawal |
| `headline/` | The Alice, Bob, Carol, and Dana test: Bob's provider advertisement, two index slices of Dana's shop, two query responses, Carol's notice, and Alice's route with its PKARR TXT values |

Records use the synthetic `pub/slime-example/` namespace. They are not native tag IDs and not a deployed listing schema. The checker's adapter for that namespace derives entries the way a real adapter does for deployed records.

Formats and their schemas in [../schemas/](../schemas/):

| Format | Schema |
|---|---|
| `slime-set/1` | `set.schema.json` |
| `slime-signature/1` (purposes `set`, `record`, `provider`) | `signature.schema.json` |
| `slime-record/1` | `record.schema.json` |
| `slime-observation/1` | `observation.schema.json` |
| `slime-provider/1` | `provider.schema.json` |
| `slime-slice/1` | `slice.schema.json` |
| `slime-candidates/1` | `candidates.schema.json` |
| `slime-notice/1` | `notice.schema.json` |
| `slime-route/1` | `route.schema.json` |
| Entries, scopes, keys, and times shared by the above | `common.schema.json` |

## Run the checker

From the repository root, with Python packages `cryptography` and `jsonschema`:

```sh
python examples/check_sets.py examples/github-signed
python examples/check_sets.py examples/headline/bob-slice-2
python examples/check_sets.py examples/headline/bob-provider
python -m unittest discover -s examples -p 'test_*.py' -v
```

The checker reads staged directories and files. It checks inventories, signatures, slices against their record bytes, advertisements, query responses against the query and the advertised scope, notices against their source record, and route pins and failover records. It does not import `github-plain/`, because that folder is valid sharing without an inventory. It does not extract archives, sign, or use the network.

`test_checks.py` covers folders, signatures, and merge. `test_headline.py` runs the headline test's data path with sockets disabled: Alice picks Bob's provider from its advertisement, imports his slice, searches Dana's listings locally, checks Carol's notice, takes Carol's tag from Bob's answer, and resolves her own homeserver through her failover record.
