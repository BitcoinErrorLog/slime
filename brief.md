# Slime

Slime is the part of Pubky a person can keep. They retain the posts, tags, and offers they use, read that set without asking an indexer what exists, and give the same files to someone else as a folder.

Pubky already separates a key from the machine that stores bytes. A **homeserver** is the host that stores a key's records. **PKARR** publishes where that homeserver is, so a client can find it from the key alone. An indexer such as Nexus can still build a large view on top. If the indexer is the only way to see people, tags, and offers, the indexer decides what is visible. A cached feed page is not enough to rebuild those relationships.

Slime draws a line between three things. The **replica** is the original records and local work stored on the device. The **index** is a view computed from those records: a feed, a tag lookup, a catalog filter. **Exchange** is handing someone a folder of the records, not a login to your indexer. A provider can add coverage. Losing one provider loses freshness, not the working set.

## What a person can do

- Keep the authors, tags, and public offers they selected, as the original bytes.
- Open the app offline, search what they kept, and compose. The draft is still there after a restart.
- Publish later, through an authorized homeserver. The indexer does not confirm publication.
- Export a folder or a ZIP. The recipient imports it and searches it without calling the sender.
- See who wrote a record, who supplied the copy, and what evidence came with it.
- Keep the public records of familiar keys fresh by fetching them from those keys' homeservers and from other people who already hold them, and by serving the public copies they already hold when asked.

Nexus stays useful for broad discovery. A read uses the local index first. Nexus fills gaps outside the familiar set. Its answers land in the replica as the authors' records, not as the indexer's ranking.

A **familiar key** is one you follow, one you mark trusted, or the seller of a shop or listing you follow. The trust mark stays on the device. Public tags by those keys, and public tags whose target you keep, are familiar records too. So are the public shop records and listings of sellers you follow, and listings you have publicly bookmarked. A private favorite fetches that public shop and its listings onto the device and indexes them there. It does not publish the favorite, and it does not add that seller to the keys you answer for. If someone already names that listing, the public bytes can be returned without saying it was a favorite.

## How trust works

A copied record is not a new endorsement. Serving a tag does not mean you agree with it. A curator's signature means that curator shipped this selection. It does not mean they wrote every file inside it. A tag remains a claim by one key about one target. Importing a key list does not follow those keys. Importing a ranking does not adopt it.

By default the app fetches and serves public records for familiar keys. That default is how offers, tags, and listings stay available when an indexer is gone. Turn serving off and the device only fetches. Searches, drafts, orders, private favorites, and anything an indexer added on its own stay on the device.

The reader chooses which sources count. Two people can hold the same files and weight them differently. Nothing in a README changes follows, trust, signing, or sharing.

Search over retained records stays on the device. A public folder contains only what the sender selected. Orders, addresses, payment requests, and drafts stay out of it. Paying is a separate step, through Paykit, against the live seller. A Lock still gates access. The folder does not reserve stock or freeze a price.

## When something fails

| What failed | What still works |
|---|---|
| The indexer | The local index still answers. Familiar keys still refresh from their homeservers and from peers who hold those public records. Anything never retained and not held by a peer is missing, and the app says so. |
| The homeserver | Local work remains. Publication waits. A spare copy is not silently promoted to the publisher. |
| The network | The installed app opens retained records and drafts across a restart. |
| A supplier omits a known record | The retained copy stays. Omission is not a deletion by the author. |
| A signed folder was altered | The import is held back. It is not treated as a trusted unsigned folder. |
| Two copies disagree | Both are kept. The reader's source rules pick one, or the conflict is shown. |

Moving the public homeserver address in PKARR is an identity action. The app does not do it by itself, and it does not take the identity seed to try.

## Limits

Slime cannot recover bytes nobody stored, learn about events while fully offline, or prove a search covered the whole network. A person who receives plaintext can copy it. An old catalog is not the current price or the current stock. A signature is not proof that a claim is true.

## Done when

Block the main indexer, restart offline, read and search the retained set, write a draft, restart again, and still have it. Two people who follow the same seller still have that seller's public tags, shop record, and listings when the indexer is down, because one of them already held the bytes. A second client imports a folder of GitHub tags and rebuilds the same attributed tags without contacting the exporter. A public catalog searches with the network blocked and contains no orders, addresses, or payment data. A private favorite never appears in what was served. A change to a signed file, the README, or an origin mapping is detected. Importing the same folder twice does not duplicate a tag. An older catalog does not bring a withdrawn listing back.
