# Slime

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **Replaceable, verifiable indexing.** Several independent indexers provide discovery and search, and any of them can be replaced. Every record carries its author's signature, so every copy and every indexer answer can be checked. Anyone can also publish a signed slice of what they keep, the smallest indexer there is. Indexers do search. Slices do not.
2. **Local fallback.** When an indexer or a homeserver is disrupted or refuses service, the app keeps working from local state and replaceable providers. Reading, search over what is retained, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable. Synonym's Nexus and Synonym's homeserver are the convenient defaults. Neither is necessary for continuity, discovery, or participation.

## The test

Alice, Bob, and Carol use Pubky App on Synonym's homeserver. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely, and Alice's app fails over to a second indexer that Synonym does not run. Then Dana's homeserver goes dark. Alice still opens Dana's shop, listings, and tags, because Bob's slice and the indexer both hold them and every copy carries Dana's signature, and she searches them offline. A forged copy of one listing, with a different price, is rejected rather than shown. Carol tags a listing, and Alice finds the tag through the indexer. Then Synonym's homeserver stops accepting Alice's writes while still serving stale reads. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, readers find it through the homeservers her PKARR record lists, and her edits follow her signed home statement. Alice's identity seed never leaves Pubky Ring.

The [development plan](development-plan.md) ends on this test and harder variants: the seller's homeserver down, the primary timing out or serving stale data, a fresh install, and everyone on Synonym's homeservers.

## Job 1: indexing that no one owns

Pubky already separates a key from the machine that stores its bytes. A **homeserver** stores a key's records. **[PKARR](https://github.com/pubky/pkarr)** publishes where that homeserver is, signed by the key itself, and can list several homeservers in priority order. An indexer such as Nexus reads many homeservers and answers the questions no single homeserver can: who follows me, who replied, what is tagged with this label. If one indexer is the only way to find people, tags, and shops, that indexer decides what is visible.

Slime makes indexers replaceable and their answers checkable:

- **Author signatures.** The app that writes a record signs it with its app key, the client key of the Pubky grant Ring gave it. Every copy, wherever it came from, can be checked against its author. A forged listing is rejected, not shown.
- **Many indexers.** The app keeps an ordered list of indexers and fails over on its own. The defaults include one Synonym does not run.
- **Signed answers.** An indexer signs what it returns, so an answer that leaves something out can be caught by comparing it with another indexer's.
- **Slices.** You choose what to share, and the app publishes the result on your homeserver as a static, signed slice. It is the smallest indexer there is: anyone can search it without anyone seeing the question, and followers can get verified copies of a shop from it when the shop's homeserver and the indexers are down. A slice does not do discovery. It only covers what you chose to share.

## Job 2: the app keeps working

The app renders from a **replica** on the device: the original records with their author signatures, your local work, where each copy came from, and an index built from those records. Every network source synchronizes with the replica. None of them is required to open it.

- Open the app offline. Read, search what you keep, and browse the shops and listings you follow, with their images when they were retained.
- Compose offline. The draft and the outbox survive restarts and expired sessions.
- Publish through your homeserver. If it refuses you, the app switches to an alternate you enrolled once through Ring. Your PKARR record lists every enrolled homeserver, so readers already know where else to look. For edits, a failover key signs a statement naming which homeserver decides.
- Configure indexers and providers once. When one fails, the next takes over. No endpoint editing during an outage.

## What is covered

The [coverage matrix](spec.md#1-coverage) has one row for each data type below. Each row says how the type is indexed and shared, how it is retained locally, what happens when a provider fails, and where its privacy boundary sits.

- **Social:** profiles, posts, replies, follows, mutes, tags, bookmarks and favorites, custom feeds.
- **Commerce:** shops, listings, offers, reviews, followed shops and followed listings, locked content.
- **What records depend on:** blobs, media, and other dependencies; author signatures and history.
- **Slime's own documents:** slices; signed indexer answers, services documents, and home statements.
- **Never shared:** the last-read marker; the private workspace; transactions.

Slime needs no shop or listing schema. A shop is a seller's key and the records the seller publishes. A listing is one of those records. Following a shop is following the seller. Following a listing is bookmarking it. Tags label listings.

## How trust works

A copy is only as good as its author signature. A slice or an indexer answer signed by someone else means "I saw this", not "the author wrote this". Several witnesses agreeing never turns a forgery into a version. Two versions both signed by the author stay as a conflict until the author's homeserver decides. Sharing a tag does not mean you agree with it, and importing a key list does not follow those keys.

Searches, drafts, carts, orders, private favorites, private follows, and trust marks stay on the device. Paying is a separate step, through Paykit, against the live seller. A Lock still gates access. A retained catalog does not reserve stock or freeze a price.

## When something fails

| What failed | What still works |
|---|---|
| The indexer | The next indexer in your list answers, including search. The local index answers first. |
| Another key's homeserver | That key's records come from the replica, its other enrolled homeservers, and author-signed copies from indexers and slices. |
| Your homeserver refuses you | Publication moves to an enrolled alternate automatically. Readers find it through your PKARR record, and your edits follow your home statement. Your mirrors keep your PKARR record alive if the primary stops republishing it. |
| The network | The installed app opens retained records, followed shops, and drafts across restarts. |
| A supplier offers a forged copy | It fails the author signature check and is rejected. |
| A signed slice or folder was altered | The import is held back. |

## Limits

Slime handles operators who refuse service or disappear, outages, and forged copies. It does not protect against state seizure of servers, and it gives no anonymity: homeservers, indexers, and relays are public servers with known operators, and your PKARR record lists your homeservers in public. Privacy and compliance are separate layers built on top.

In a browser, the app resolves PKARR through relays, syncs only while a tab is open, and can lose its storage in Safari after a week without use unless it is on the Home Screen. A companion or native app gives the guarantees a browser can't. Readers cannot see a grant's revocation, so a revoked key's earlier signatures verify until the grant expires. Slime cannot recover bytes nobody stored or prove a search covered the whole network. An old catalog is not the current price or stock.
