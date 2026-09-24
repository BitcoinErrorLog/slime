# Reference sets

Synthetic folders for the Slime folder format. Public keys and Ed25519 signatures are real. There are no private keys, and no real seller or order.

`github-plain/` is a folder with no inventory. `github-inventoried/` adds an unsigned inventory. `github-signed/` adds an exporter signature. `github-history/`, `github-fork/`, and `github-joined/` cover deletion, concurrent edits, and a join. `shops-public/` and `shops-withdrawn/` cover a public catalog and a later withdrawal.

Records use the synthetic `pub/slime-example/` namespace. They are not native tag IDs and not a deployed listing schema.

## Run the checker

From the repository root, with Python packages `cryptography` and `jsonschema`:

```sh
python examples/check_sets.py examples/github-signed
python examples/check_sets.py examples/shops-public
python -m unittest discover -s examples -p 'test_*.py' -v
```

The checker reads a staged directory. It checks the optional inventory, supported signatures, and the fixture bodies. It does not import `github-plain/`, because that folder is valid sharing without an inventory. It does not extract archives, sign, or use the network.
