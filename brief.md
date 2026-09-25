# Slime

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **P2P indexing.** People share what they already know: records, tags, follows, shops, listings, and slices of their own index. The network stays densely indexed without any single indexer, and anyone can discover it and crawl it.
2. **Local fallback.** When an indexer or a homeserver is disrupted or censored, the app keeps working from local state and replaceable providers. Reading, search, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable. Synonym's Nexus and Synonym's homeserver are the convenient defaults. Neither is necessary for continuity, discovery, or participation.

## The test

Alice, Bob, and Carol use Pubky App. Dana sells prints from her own homeserver.

Synonym's Nexus disappears completely. Alice follows Dana. Bob already retains Dana's shop, listings, and tags, and his Slime provider advertises that scope. Alice's app finds Bob's provider through her configured mesh, pulls Dana's shop, listings, and tags, builds them into her local index, and searches them offline.

Carol publishes a new tag on one of Dana's listings. Alice sees it through Bob's index or a notice, with no Synonym service involved.

Then Synonym's homeserver starts refusing Alice's writes. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, her public location moves to that alternate, and Bob and Carol read the post. Alice's identity seed never leaves Pubky Ring.

When that works, Slime works. The [development plan](development-plan.md) ends on this test.

## Job 1: the network indexes itself

Pubky already separates a key from the machine that stores its bytes. A **homeserver** stores a key's records. **[PKARR](https://github.com/pubky/pkarr)** publishes where that homeserver is, signed by the key itself. An indexer such as Nexus builds a large view on top. If that indexer is the only way to find people, tags, and shops, the indexer decides what is visible.

Slime spreads that job across everyone who already holds the data:

- **Entries.** Every retained record reduces to one line: its URI, kind, hash, and what it references. An entry is a candidate. The receiver checks it against the bytes and indexes it locally.
- **Index slices.** A provider signs a folder of entries for a scope it chose, such as one seller's key, and publishes it on its own homeserver. Anyone can download it and search it privately. The provider never sees the search.
- **Live queries.** A provider that runs an endpoint answers four questions: records by a key, tags with a label, records that reference a URI, and links to a domain. Answers are candidate lists, never rankings.
- **Advertisements.** A provider signs a small statement: its endpoint, its roles, the scopes it retains, its current slices, and a few peers. PKARR can point at it. No registry is required.
- **Notices.** When a stranger replies to you, tags your listing, or follows you, their client tells your chosen notice providers where the record is. The providers check it and index it. You fetch it and check it again.

Your app shares the public records of the keys you follow, including the shops and listings you follow publicly, as a slice on your own homeserver. That default keeps offers, tags, and listings findable when an indexer is gone. Turn it off and your app only fetches.

## Job 2: the app keeps working

The app renders from a **replica** on the device: the original records, your local work, where each copy came from, and an index built from those records. Every network source synchronizes with the replica. None of them is required to open it.

- Open the app offline. Read, search, and browse the shops and listings you follow, with their images when they were retained.
- Compose offline. The draft and the outbox survive restarts and expired sessions.
- Publish through your homeserver. If it refuses you, the app switches to an alternate you enrolled once through Ring. A scoped failover key moves your public location among those alternates. It cannot do anything else.
- Configure providers once. When one fails, the next eligible one takes over for that role and scope. No endpoint editing during an outage.

Reads go outward only as far as needed: your local index, then slices you already hold, then a live peer, then the author's homeservers, then a large indexer, then its alternates. Each step outward adds a witness, so the nearest answer wins.

## What is covered

The [coverage matrix](spec.md#1-coverage) has one row for each data type below. Each row says how the type is shared and crawled, how it is retained locally, what happens when a provider fails, and where its privacy boundary sits.

- **Social:** profiles, posts, replies, follows, mutes, tags, bookmarks and favorites, custom feeds, notices and mentions.
- **Commerce:** shops, listings, offers, reviews, followed shops and followed listings, locked content.
- **What records depend on:** blobs, media, and other dependencies; proofs, signatures, and history.
- **Slime's own documents:** index slices; provider advertisements and routes.
- **Never shared:** the private workspace; transactions.

Followed shops and followed listings get their own row because they carry both jobs. A public follow makes the seller part of what you retain and share. A private follow is a favorite: the app retains and indexes the shop, all its listings, the tags and reviews on them, and their images, and none of that preference leaves your device.

## How trust works

A copied record is not a new endorsement. Serving a tag does not mean you agree with it. A provider's signature means that provider shipped this slice. It does not mean it wrote the records inside. A tag remains a claim by one key about one target. Importing a key list does not follow those keys. Importing a ranking does not adopt it, and Slime never ships one.

The reader chooses which sources count. Two people can hold the same files and weight them differently. Nothing in a README or an advertisement changes follows, trust, signing, or sharing.

Searches, drafts, carts, orders, private favorites, private follows, and trust marks stay on the device. A public folder contains only what the sender selected. Paying is a separate step, through Paykit, against the live seller. A Lock still gates access. A retained catalog does not reserve stock or freeze a price.

## When something fails

| What failed | What still works |
|---|---|
| The indexer | The local index answers. Slices and live peers fill gaps. Familiar keys refresh from their homeservers. The app says what it could not reach. |
| Another key's homeserver | That key's records come from the replica, its other enrolled homeservers, its mirrors, peers, and slices. |
| Your homeserver refuses you | Publication moves to an enrolled alternate automatically. Slime readers follow. Other clients follow once Ring moves the main record, and the app says when that has not happened yet. |
| A notice provider | The sender tries your other notice providers. Peers' answers carry the same references. |
| The network | The installed app opens retained records, followed shops, and drafts across restarts. |
| A supplier omits a known record | The retained copy stays. Omission is not a deletion by the author. |
| A signed slice or folder was altered | The import is held back. It is not treated as a trusted unsigned folder. |
| Two copies disagree | Both are kept. The reader's source rules pick one, or the conflict is shown. |

## Limits

Slime cannot recover bytes nobody stored, learn about events with no path to anyone, or prove a search covered the whole network. Advertisements do not stop a hostile set of providers from hiding a record. Cross-checking with the author's homeserver narrows that. Publishing failover needs one enrollment through Ring beforehand, and clients that do not implement Slime keep reading the old homeserver until Ring moves the main record. Edits to mutable records wait for a conditional write on the homeserver before they fail over. A person who receives plaintext can copy it. An old catalog is not the current price or the current stock. A signature is not proof that a claim is true.
