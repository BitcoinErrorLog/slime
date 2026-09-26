# Slime

Slime (Social Latent Intelligence Mesh Exchange) has two jobs on Pubky.

1. **Replaceable, verifiable indexing.** Several independent indexers provide discovery and search, and any of them can be replaced. Every record carries its author's signature, so every copy and every indexer answer can be checked. Anyone can also publish a signed slice of what they keep, the smallest indexer there is. Indexers do search. Slices do not.
2. **Local fallback.** When an indexer or a homeserver is disrupted or refuses service, the app keeps working from local state and replaceable providers. Reading, search over what is retained, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable. Identity stays a Pubky key. Publishing stays on homeservers the user chose.

**Done when:** Alice, Bob, and Carol use Pubky App on Synonym's homeserver. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely, and Alice's app fails over to a second indexer that Synonym does not run. Then Dana's homeserver goes dark. Alice still opens Dana's shop, listings, and tags, because Bob's slice and the indexer both hold them and every copy carries Dana's signature, and she searches them offline. A forged copy of one listing, with a different price, is rejected rather than shown. Carol tags a listing, and Alice finds the tag through the indexer. Then Synonym's homeserver stops accepting Alice's writes while still serving stale reads. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, readers find it through the homeservers her PKARR record lists, and her edits follow her signed home statement. Alice's identity seed never leaves Pubky Ring.

Read in this order:

1. [Brief](brief.md): the two jobs, the test, what a person gets, and the limits.
2. [Specification](spec.md): the coverage matrix, the replica and author signatures, sharing controls, replaceable indexers and signed answers, slices, routing, keys and publishing failover, folders, the commerce boundary, and limits.
3. [Development plan](development-plan.md): phases toward the test, the repos each one touches, and the gate that closes it.
4. [Examples](examples/README.md): reference fixtures, JSON schemas in [schemas/](schemas/), and a Python checker with its tests.

License: [LICENSE](LICENSE)
