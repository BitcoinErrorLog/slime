# Slime

Slime (Social Latent Intelligence Mesh Exchange) has two jobs on Pubky.

1. **P2P indexing.** Peers share what they already know: records, tags, follows, shops, listings, and whatever parts of their own index they choose to share. The network stays densely indexed without any single indexer, and anyone can discover it and crawl it.
2. **Local fallback.** When an indexer or a homeserver is disrupted or censored, the app keeps working from local state and replaceable providers: read, search, browse followed shops and listings, compose, and publish. The switch is automatic.

Synonym and every other provider is automatically replaceable. Identity stays a Pubky key. Publishing stays on homeservers the user chose.

**Done when:** Synonym's Nexus disappears completely. Alice follows Dana's shop, finds the Slime provider of Bob, who chose to share Dana's records, pulls Dana's shop, listings, and tags from it, and searches them offline. Carol tags one of Dana's listings, and Alice sees it through Bob's index or a notice. Synonym's homeserver refuses Alice's writes, her pre-enrolled alternate accepts her next post, and Bob and Carol read it. Alice's identity seed never leaves Pubky Ring.

Read in this order:

1. [Brief](brief.md): the two jobs, the test, sharing controls, what a person gets, and the limits.
2. [Specification](spec.md): the coverage matrix, the replica, sharing controls and shared indexes, the query interface, advertisements, notices, routing, keys and publishing failover, folders, and the commerce boundary.
3. [Development plan](development-plan.md): phases toward the test, the repos each one touches, and the gate that closes it.
4. [Examples](examples/README.md): reference fixtures, JSON schemas in [schemas/](schemas/), and a Python checker with its tests.

License: [LICENSE](LICENSE)
