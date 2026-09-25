# Slime specification

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **P2P indexing.** Peers share what they already know: records, tags, follows, shops, listings, and slices of their own index. The network stays densely indexed without any single indexer. Anyone can discover the peers and crawl what they share.
2. **Local fallback.** When an indexer or a homeserver is disrupted or censored, the app keeps working from local state and replaceable providers. Reading, search, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable. Synonym's Nexus and Synonym's homeserver are defaults, not dependencies.

**Headline test.** Alice, Bob, and Carol use Pubky App. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely. Alice follows Dana. Bob already retains Dana's shop, listings, and tags, and his Slime provider advertises that scope. Alice's app finds Bob's provider through her configured mesh, pulls Dana's shop, listings, and tags, builds them into her local index, and searches them offline. Carol publishes a new tag on one of Dana's listings. Alice sees it through Bob's index or a notice, with no Synonym service involved. Then Synonym's homeserver starts refusing Alice's writes. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, her public location moves to that alternate, and Bob and Carol read the post. Alice's identity seed never leaves Pubky Ring.

Every rule below serves one of the two jobs or protects a boundary between them. The [development plan](development-plan.md) ends on the headline test.

Requirements use MUST, SHOULD, and MAY.

## Terms

- **Homeserver.** The host that stores a key's records.
- **[PKARR](https://github.com/pubky/pkarr).** Signed DNS records on the Mainline DHT. Each key signs its own packet, which says where its homeserver is.
- **Replica.** The device's copy of original bytes, local work, provenance, and a derived index. The app renders from it.
- **Entry.** One line of an index: a record URI, its kind, its hash, and what it references. An entry is a candidate, not a verdict.
- **Index slice.** A signed folder of entries for a declared scope, with or without the records themselves.
- **Provider.** A key that serves Slime roles: a person's companion, a community archive, a large indexer. It signs an advertisement with its own provider key.
- **Route.** An identity's enrolled homeservers, failover key, notice providers, and mirrors. Its hash is pinned in the identity's PKARR packet.
- **Failover key.** A scoped key that may choose which enrolled homeserver is active. It is not the identity key.
- **Notice.** A pointer that says: this public record references you, fetch it here.
- **Familiar scope.** The public records a device collects and shares by default (section 3).

Three conformance levels:

- **Exchange.** Import and export folders and slices. Verify inventories and signatures. Preserve provenance. Follow the merge and disclosure rules.
- **Replica.** Exchange, plus a durable workspace, a local index built from originals, the replica interface, familiar-scope collection with dependencies, provider routing with automatic replacement, slice and live-query use, notices sent and drained, and publishing failover once enrolled. This is the Pubky App target.
- **Provider.** Serve a signed advertisement and one or more roles: `records`, `query`, `slices`, `notices`.

A client MUST say which levels it implements.

## 1. Coverage

This matrix is the scope of Slime. Each row says how a data type serves job 1 (shared and crawled), how it serves job 2 (retained locally, and what happens when a provider fails), and where its privacy boundary sits. A data type that is not in this matrix is outside Slime.

| Data type | Shared and crawled (job 1) | Retained locally (job 2) | When a provider fails (job 2) | Privacy boundary |
|---|---|---|---|---|
| Profiles | Entry kind `profile`. In slices and `author` answers for every key in a provider's scope. | Own profile, familiar keys, and the author of every retained record, as a dependency. | Renders from the replica. Refreshes from the key's enrolled homeservers, mirrors, and peers. | Public record only. |
| Posts | Kind `post`. In `author` answers and slices. Links in posts answer `domain`. | Own posts, familiar keys' posts, and posts the user opened. | The following feed is built locally from retained authors. New posts arrive from homeservers and peers. Composing goes to the outbox. | An opened post outside the familiar scope is kept, not shared. |
| Replies | Kind `post` with the parent in `refs`. In `refs(parent, kind=post)` answers. The replier sends a notice to the parent's author. | Replies to own posts, replies in retained threads, and each reply's parent as a dependency. | Replies from unknown keys arrive by notice or a peer's `refs` answer. A thread shows how much of it was consulted. | Public records only. |
| Follows | Kind `follow`, with the followed key in `refs`. `author(K, kind=follow)` lists a key's follows. `refs(pubky://K/, kind=follow)` lists its known followers. | Own follows, which define the familiar keys. Familiar keys' follows, for trust paths. | The graph is local. New followers arrive by notice. | Public follows are shared. A local trust mark is never shared. |
| Mutes | Kind `mute`, with the muted key in `refs`. Shared with the author's other public records. | Own mutes, and familiar keys' mutes as filter input. | Filters run locally. | Public mute records only. A local hide list stays local. |
| Tags | Kind `tag`, with `label` and the target in `refs`. In `label` and `refs(target, kind=tag)` answers. The tagger sends a notice to the target's author. | Own tags, tags by familiar keys, and tags whose target is retained. | Tag lookups run locally. New tags arrive from peers, slices, and notices. | A tag stays a claim by its author. Serving it is not agreeing with it. |
| Bookmarks and favorites | A public bookmark is kind `bookmark`, with the target in `refs`. A private favorite is never an entry. | Both. Either one pins the target and its dependencies. | Bookmarked and favorited items open offline. | A private favorite is never exported, advertised, served, or answered for. Someone who names the target URI may receive its public bytes, with no favorite flag. |
| Custom feeds | Kind `feed` for a published feed definition. | Own feed definitions. Feeds are evaluated locally over the replica. | A feed runs offline and shows what it consulted. | Public definitions only. Searches stay local. |
| Shops | Kind `shop`. In `author(seller, kind=shop)` answers and slices, and held by the seller's mirrors. | Shops of followed sellers and of followed or favorited listings, with the seller profile and media within budget. | The shop page renders from the replica. It refreshes from the seller's enrolled homeservers, mirrors, and peers. | Public records only. |
| Listings | Kind `listing`, with the shop and media in `refs`. In `author(seller, kind=listing)` and `refs(shop)` answers and slices. | Every listing of a followed shop, and every followed or favorited listing, with images within budget. | Catalog search runs offline. An admitted withdrawal beats an older copy. Price and stock show the time they were retrieved. | Public records only. A copy reserves nothing. |
| Offers | Public offer terms (price unit, availability, auction terms) are listing fields and travel with the listing. Buyer offers, bids, and counter-offers are never shared. | Terms, with the listing. The user's own offers stay in the workspace or with the transaction service. | Terms show the time they were retrieved. Making an offer needs the live seller through Paykit. It queues and is not shown as sent until the seller's side accepts it. | Buyer offers are transaction data. |
| Reviews | Kind `review`, with the listing or shop in `refs`. In `refs(listing, kind=review)` answers. The reviewer sends a notice to the seller. | Reviews on retained shops and listings. | Read locally. New reviews arrive from peers and notices. | A review is its author's claim. An attestation is checked under its own rules. |
| Followed shops and followed listings | Public form: a follow of the seller's key or a public bookmark of the listing. The seller becomes familiar, and the user's slice and provider cover the seller's key. Private form: nothing leaves the device. | Both forms pin the shop record, all of its listings, the seller profile, tags and reviews on them, and media within budget. They refresh from the seller's homeservers, mirrors, peers, and slices. | Browsing and search work offline. While the seller's homeserver is down, updates come from peers and mirrors that hold the seller's key scope. | A private follow follows the favorite rules. A public follow is a public record. |
| Blobs, media, and other dependencies | Kinds `blob` and `file`. Served by any holder. A slice that carries bodies carries their public dependencies. | Tracked per record as retained, missing, fetchable, or withheld (section 2.4). Text first, media within budget. | A missing image shows as missing. Network-quiet mode does not fetch it. Any holder can supply it, and the hash decides. | Locked bytes are withheld. Private uploads stay private. |
| Notices and mentions | A notice points a key's notice providers at a public record that references the key. The provider checks it and indexes it, so it answers `refs`. A mention is a post with the mentioned key in `refs`. | Drained into the replica after the source is checked. Notifications and their read state are derived locally. | Each key lists several notice providers. Peers' `refs` answers carry the same references. | Pointers to public records only. No bodies. Unknown senders are filtered locally. |
| Index slices | Signed by a provider. Thin (entries) or full (entries and records). Published on the operator's homeserver or endpoint and mirrored by anyone. | Imported slices merge into the replica, with the provider recorded as supplier. | Slices answer locally with no witness. Live `after` queries top them up. | Public entries only, drawn from public follows, public bookmarks, and explicit scope choices. |
| Provider advertisements and routes | Pinned in PKARR, stored on homeservers and endpoints, carried in folders. Crawlable. | The provider table, with health per role and scope. | Cached copies keep routing working while a homeserver is down. | Public by design. They state scopes, never queries. |
| Proofs, signatures, and history | Author proofs, set signatures, and earlier versions travel unchanged with records in folders and full slices. | Kept in the record store with each retained version. | Verification runs offline. A missing proof stays a gap, never a pass. | The signer's key is visible. An identity key signs only through Ring. |
| Private workspace | Never shared. | Drafts, outbox, read state (including the App's last-read marker), searches, carts, notes, and trust marks. Survives session failure. | Compose and queue offline. | Never in folders, slices, answers, or notices. An encrypted backup goes only to a destination the user chose. |
| Transactions | Never shared. | Held by Paykit, the transaction service, or an encrypted backup the user chose. | Queued until the live counterparty answers. | Inquiries, buyer offers and bids, orders, addresses, invoices, payment requests, receipts, and messages never enter a public set. |
| Locked content | Only the public preview fields the listing publishes. | Unlocked bytes stay in the workspace under the Lock's terms. | Unlocking needs the live Lock. | Locked bytes are never served, sliced, or exported. |

Entry kinds are `profile`, `post`, `follow`, `mute`, `tag`, `bookmark`, `feed`, `shop`, `listing`, `review`, `file`, `blob`, and `other`. Replies and mentions are posts. Offers are listing fields. Notices, slices, advertisements, and routes are Slime documents. Proofs and signatures are evidence attached to versions. The workspace, transactions, and locked bytes never become entries.

Slime defines no post, shop, or listing schema. Adapters read the deployed Pubky App and shop records and emit entries. A type without an adapter is kept as opaque bytes with kind `other`. It MUST NOT be read as another type.

## 2. The replica

### 2.1 Records

A logical record is `pubky://<author>/<path>`, checked with the existing SDK. The author key is not the homeserver hostname and not the key of whoever supplied the copy.

A retained version is the origin URI plus the SHA-256 of the exact original bytes. Identical bytes MAY share a blob. Origin mappings MUST stay distinct. This digest MUST NOT replace native Pubky IDs or the native BLAKE3 content hash.

Three stores, even when one database holds them:

| Store | Holds | Rule |
|---|---|---|
| Workspace | Drafts, outbox, read state, private settings, trust marks, favorites, carts, orders | Session failure MUST NOT erase it. It is not a cache. |
| Record store | Original bytes, origins, suppliers, proofs, source notes, deletion evidence | Normalization MUST NOT rewrite these bytes. |
| Derived index | Entries, feeds, tag lookups, catalogs, local search | Rebuildable from the record store. A provider's counts and scores stay labeled as that provider's claims. |

### 2.2 The replica interface

The app renders from the replica. Every network source synchronizes with it. In a browser the replica is in-process storage, not an HTTP server.

```text
Replica
  get(uri, version?)         original bytes and provenance, or a typed absence
  list(key, prefix, cursor)  retained records under a key and path
  putLocal(uri, bytes, op)   a local write and its outbox row
  deleteLocal(uri, op)       a local delete and its outbox row
  events(scope, cursor)      local changes, for the index and the sync loops
  versions(uri)              retained versions with suppliers and evidence
  dependencies(uri)          what the record needs, and the state of each
  query(op, args, cursor)    the primitives of section 4.3, over retained entries
```

`putLocal` and `deleteLocal` record intent. They MUST NOT report that a homeserver accepted anything. A record under another key MAY be retained. It MUST NOT be edited or deleted locally as if the reader authored it. `query` uses the same four primitives and the same ordering as a live provider, so a slice, a live answer, and the local index are interchangeable inputs.

Four absences stay distinct: the source is unavailable, the client has not looked, the source reports the record gone, and an authenticated deletion. An indexer's omission is never an author deletion. Dropping a record from a personal scope is a retention choice, not an author deletion.

### 2.3 Sync architecture

```text
            +--------------------------- Replica ---------------------------+
            |  workspace  |  record store  |  derived index                 |
            |  outbox, cursors, provenance, provider table, health          |
            +-------------------------------+-------------------------------+
                                            |
        +-----------------------------------+-----------------------------------+
        |                                   |                                   |
  Homeserver sync                       Mesh sync                         Indexer sync
  publish own records,             slices in and out,                 broad coverage from
  replicate to enrolled            live peer queries,                 any large indexer,
  homeservers, collect             notices, serving                   as one provider
  familiar keys' events            through a provider                 among several
```

The three loops are independent. A failed indexer does not stop publication. A failed publishing session does not stop browsing. A failed media source does not invalidate a text record.

Each adapter keeps its own cursor, bound to that provider and that scope. A cursor MUST NOT be reused between providers, or after a suspected reset. Persist the event, and any pending body fetch, before moving the cursor forward. A newer body at a path MUST NOT be attached to an older event's hash. Directory order is not time order. Event positions and entry `seq` values that can exceed JavaScript's safe integer range MUST be stored as decimal strings.

Fetchers MUST limit URL schemes, refuse local and metadata addresses unless the user allowed them, check redirects, cap response size, and MUST NOT send one origin's credentials to another. Keys and links in an import are not permission to crawl.

### 2.4 Dependencies

A retained listing without its shop and images is not a working shop. Adapters list each record's dependencies: the author's profile, a reply's parent, a tag's target, a listing's shop and seller profile, and media blobs and files. For each dependency the replica records one state:

| State | Meaning |
|---|---|
| `retained` | The bytes are in the record store and match the expected hash. |
| `missing` | No copy is held and no holder is known. |
| `fetchable` | No copy is held. A provider, peer, or origin is known to hold it. |
| `withheld` | Locked, private, or over the media budget. |

Text dependencies of a retained record are fetched with it. Media follows the media budget. A pinned item (an own record, a followed shop, a followed listing, a favorite) pins its dependencies within that budget. A record with a missing dependency renders with the gap shown. It MUST NOT present a missing image as a removal by the seller.

Any holder MAY serve a public dependency. The receiver MUST check the bytes against the hash the referencing record or path names before use. A provider that serves a record SHOULD serve the public dependencies it holds. A full slice SHOULD carry them.

## 3. Familiar scope and retention

A key is **familiar** when the user follows it, marks it trusted, or it is the seller of a shop or listing the user follows. A trust mark is a local policy. It is not a shared record and not an endorsement.

A record is in the **familiar scope** when any of these is true:

- The user authored it.
- A familiar key authored it, and it is public. This includes posts, follows, mutes, tags, reviews, shop records, and listings.
- It is a public tag, reply, or review whose target the user already keeps.
- It is a public shop record or listing for a seller the user follows, or a listing the user has publicly bookmarked.

**Followed shops and followed listings** come in two forms. The public form is a published follow of the seller's key or a public bookmark of the listing. It makes the seller familiar, and it is shared like any other public record. The private form is a workspace pin (a private favorite). It MUST cause the client to fetch and retain the public shop record, all of its listings, the seller profile, the tags and reviews on them, and their dependencies within budget, and to index them locally. It MUST NOT be exported, advertised, served, or answered for. The client MUST NOT add that seller to the familiar keys because of the pin alone. If a peer names that listing's URI, the client MAY return the public bytes, with the author unchanged, and without any field that says it was a favorite.

The homeserver sync loop collects the familiar scope during ordinary use, so an outage is never the first time those records are fetched. For keys the user follows or pins, resolve the homeserver with the SDK (the active one from the route, section 7.4) and read scoped events. Group keys by host.

Starting budgets, to be measured on phones: no automatic graph expansion, 4 requests in flight, 2 per host, a 128 MiB text target, and media on demand in its own budget. Text comes before media. A phone that cannot hold its pinned scope asks for a companion. It MUST NOT evict pins.

Sharing is on by default. A Replica client shares its public familiar scope through a slice on its own homeserver (section 4.2) and through a companion provider when one is enrolled. The user can turn sharing off and keep fetching, or turn both off. Opening a record outside the familiar scope MUST NOT add it to what is shared. A private read MUST NOT start sharing.

## 4. Sharing and crawling (job 1)

A Slime peer shares what it already holds, in a form others can index without trusting it. Four pieces do that: entries, slices, a small query interface, and signed advertisements that say who serves what.

### 4.1 Entries

An entry describes one retained version:

| Field | Meaning |
|---|---|
| `seq` | The provider's own observation number, a decimal string. Strictly increasing within one provider. |
| `uri` | The record's `pubky://<author>/pub/...` URI. |
| `kind` | One of the kinds in section 1. |
| `sha256` | SHA-256 of the original bytes. Absent only on a `gone` entry. |
| `refs` | Sorted URIs the record references: tag target, reply parent, followed or muted or mentioned key (`pubky://<key>/`), bookmark target, a listing's shop and media, links. |
| `label` | The tag label. Tags only. |
| `gone` | The provider's source reports the record gone. Not an author deletion. |

`kind`, `refs`, and `label` are derived from the original bytes by the adapter. A receiver that holds the bytes MUST derive them again and reject an entry that disagrees. An entry MUST NOT carry a score, rank, count, reputation, or any field not listed. The schema is `schemas/common.schema.json#/$defs/entry`.

### 4.2 Index slices

A slice is a folder (section 8) whose `set.json` is signed by the provider key, with a `slice.json` in format `slime-slice/1`:

| Field | Meaning |
|---|---|
| `provider` | The provider key. MUST equal the set signer. |
| `as_of` | UTC time the slice was cut. |
| `scopes` | The declared scopes (section 4.4). |
| `through` | The highest `seq` the slice covers. |
| `entries` | Entries in strictly ascending `seq` order, every one inside a declared scope. |

A **thin** slice carries entries only. A **full** slice also carries the records under `records/<author>/<path>`, their proofs, and their public dependencies. Every record body in a slice MUST have an entry with the same URI and hash. The next slice from the same provider names the previous one in `set.json` `previous`.

Slices live at the operator's namespace (`pubky://<operator>/pub/slime/slices/<n>/`), at a provider endpoint, and at any mirror. Anyone MAY mirror a slice, because the signature and the hashes travel with it. A torrent MAY carry a slice snapshot. Nothing requires one.

A receiver verifies the set, checks that the signer is the slice's provider, checks order and scope, checks each carried body against its entry, and imports the bodies with the provider recorded as supplier. Thin entries become fetch candidates. The provider never learns what the receiver searches afterward. That is why the read order (section 6.3) puts retained slices before any live lookup.

A Replica client with sharing on SHOULD publish a thin slice of its public familiar scope to its own homeserver at least daily, and when that scope changes. That makes every user's homeserver a passive index host, with no server process on the device.

### 4.3 Live query interface

A provider with the `query` role answers four deterministic primitives. Each returns candidate entries, never rankings.

| Operation | Parameters | Returns entries whose |
|---|---|---|
| `author` | `key`, optional `kind` | URI is under that key: a key's posts, tags, follows, shop, listings |
| `label` | `label` | kind is `tag` with that label |
| `refs` | `uri`, optional `kind` | `refs` contain that URI: tags on a target, replies, followers, mentions, reviews, bookmarks, listings of a shop |
| `domain` | `host` | `refs` contain an http or https link to that host |

Every operation takes an optional `after`: only entries with a greater `seq`. That turns every query into a change feed. "Listings by this seller updated since my last slice" is `author(seller, kind=listing, after=through)`.

HTTP binding, relative to an advertised endpoint:

| Request | Response |
|---|---|
| `GET {endpoint}/provider.json`, `GET {endpoint}/provider.sig.json` | The advertisement and its signature. |
| `GET {endpoint}/query?op=...&...&after=...&limit=...` | `slime-candidates/1`. `400` for an unsupported operation or parameter. |
| `GET {endpoint}/record?uri=...&sha256=...` | The original bytes, or `404`. With `sha256`, a different version MUST NOT be returned. |
| `POST {endpoint}/notice` | `202` accepted for checking, `400` malformed, `403` not served here, `413` too large, `429` rate limited. |

A `slime-candidates/1` response names the `provider`, echoes the `query`, gives `as_of`, lists `entries` in ascending `seq` order, and says whether it is `complete`. `complete` means complete over the provider's declared scopes, never over the network. An incomplete response gives `next`, the `seq` of its last entry, to pass as `after`. A response holds at most the advertised `max_entries`, and never more than 1,000. The same query against the same provider state MUST return the same response. Every entry MUST match the query and fall inside the advertised scopes. An unsupported operation MUST fail. It MUST NOT return an empty success.

There is no free-text search, no arbitrary predicate, and no remote ranking. The receiver fetches the records and does that work locally.

### 4.4 Provider advertisements

A provider publishes `slime-provider/1`, signed with signature purpose `provider` by the provider key:

| Field | Meaning |
|---|---|
| `provider` | The provider key. MUST equal the signer. |
| `operator` | Optional. The identity that runs it. |
| `sequence` | Increases with every change. The highest valid sequence replaces the others. |
| `issued_at`, `expires_at` | Validity window. An expired advertisement is ignored. |
| `endpoints` | HTTPS base URLs. Required when the roles include `records`, `query`, or `notices`. |
| `roles` | Any of `records`, `query`, `slices`, `notices`. |
| `scopes` | What it retains: `{"key": K}`, `{"label": L}`, or `{"host": H}`. |
| `slices` | Current slices: location, set id, and `through`. Present exactly when the role list has `slices`. |
| `peers` | Other provider keys a crawler can visit next. At most 64. |
| `limits` | `max_entries` per response and `requests_per_minute`. |

A key scope covers the records the key authored and the public records that reference the key or its records. A label scope covers tags with that label. A host scope covers records that link to that host.

The provider key is a service key held by the provider process. It MUST NOT be an identity seed. The `operator` field is a claim. A reader treats it as confirmed only when the advertisement is published under the operator's namespace (`pubky://<operator>/pub/slime/provider.json`) or the operator's route lists the provider key.

Advertised key scopes MUST come from the operator's public follows and public bookmarks, or from an explicit choice. They MUST NOT come from trust marks or private favorites.

An advertisement lives at its endpoint, under its operator's namespace, and inside folders at `providers/<provider-key>.json` with `providers/<provider-key>.sig.json`. The provider key MAY also publish its own PKARR packet with a TXT record named `_slime`:

```text
v=slime1 ad=<sha256 hex of provider.json> ep=<endpoint or pubky:// location>
```

The provider key signs that packet itself. No identity key is involved.

### 4.5 Discovery

The **configured mesh** is the set of providers a client may use:

1. Providers the user added.
2. The defaults the app ships. A Synonym-operated provider sits in the same table as the others, with no special case. Defaults SHOULD include at least one independent operator per role where one exists.
3. Providers operated by familiar keys: advertisements published under their namespaces (`pubky://<key>/pub/slime/provider.json`) and provider keys listed in their routes.
4. Mirrors and notice providers named in familiar keys' routes, for those keys' scopes only.
5. Providers named in `peers` of advertisements already held, within the crawl budget.

For a need (a key, a label, a host), the client picks providers whose advertisement covers it, whose role fits, and whose health is good for that role and scope. It orders them by user policy, then prefers different operators. It asks at most 2 providers per live lookup, as a starting value.

A reference to a provider is a lead, not trust. Bytes are checked against hashes whatever the carrier. Advertisements do not prevent an eclipse by hostile providers. When the author's homeserver is reachable, the homeserver sync loop cross-checks it within budget.

### 4.6 Crawling

Anyone can crawl the mesh. Start from any key or provider. Follow routes to providers, mirrors, and notice providers. Follow advertisements to their `peers` and slices. Follow slice entries to more keys. Follow homeserver event streams for broad coverage. A new large indexer can bootstrap this way with no Synonym service.

Crawlers respect advertised limits and index public records only. Following a reference is one hop at a time, under the crawler's own budget. Nothing floods the mesh.

### 4.7 Witnesses

Each step outward adds a witness to what the user is looking for. So the rules are:

- Local answers come first: the local index, then retained slices.
- A live query names only the key, URI, label, or host the user asked about. Label and domain lookups SHOULD use slices before live providers.
- A client MUST NOT broadcast a search. A provider MUST NOT forward a request to another provider or to an indexer.
- A query marked private MUST NOT reach a public provider, even when its private provider fails.
- Serving a record does not endorse it, follow its author, or adopt its tag. An indexer's score, rank, cursor, or query log is not a record and MUST NOT be served.

## 5. Notices

A reply, tag, follow, review, or mention from a key the recipient does not collect is invisible until something points at it. No third party can write to another key's homeserver. So the pointer goes to providers the recipient chose.

A notice is `slime-notice/1`:

| Field | Meaning |
|---|---|
| `source` | The public record that references the recipient. |
| `target` | The referenced record, or `pubky://<key>/` for a follow or a mention. |
| `sha256` | Optional. The hash of the source bytes the sender published. |
| `created_at` | UTC time. |

A notice has no body, no preview text, and no relation type. The recipient learns the relation from the source record, not from the notice.

**Sender.** After publishing a record that references key X, the sender's client posts a notice to each notice provider in X's route, and MAY post to up to 2 providers that advertise X's key scope. It retries failed providers with backoff for 7 days.

**Provider.** A provider accepts a notice for X only when X's route lists it as a notice provider, or X is in its key scope. It rate-limits per source author and per target key. Starting values: 100 notices per source author per hour, and 1,000 per target key per hour. Before serving anything, it fetches the source from the author's homeserver (or a copy whose hash matches `sha256`), checks that the source references the target, and indexes it as an entry. It then answers `refs` for the target and appears in the provider's slices. An unchecked notice MUST NOT be served.

**Recipient.** The recipient's client asks its notice providers `refs(pubky://X/)` and `refs(<its records>)` with `after`, or reads their slices. It admits each source under the normal evidence rules and derives the notification locally. Notices from keys outside the recipient's trust paths go to a separate requests view. A notice MUST NOT follow, trust, or auto-accept anyone.

A notice provider learns that one public record references another. The record already says so in public. Private messages stay on their own channels.

## 6. Providers, routing, and automatic replacement (job 2)

### 6.1 Roles

Each role is granted on its own, per provider:

| Role | What it does |
|---|---|
| `publish` | Accepts the user's own writes. A homeserver. |
| `replicate` | Holds a copy of the user's authored public records. An enrolled homeserver. |
| `read` | Serves another key's records. That key's homeservers. |
| `records`, `query`, `slices`, `notices` | Slime provider roles (section 4). |
| `index` | Broad search and feeds. A large indexer such as Nexus. |
| `resolve` | Resolves PKARR. A relay or the DHT. |
| `backup` | Holds an encrypted private backup. |

A role MUST NOT be inferred from a README, from an advertisement the user did not accept, or from a different role.

### 6.2 The provider table

The client keeps a local provider table: each provider's key or URL, operator, granted roles, scopes, privacy class (public or private), order, credential handle, cursors, and health per role and scope. It is configuration on the device, not a public registry. The user sets policy once. The client then chooses and replaces providers on its own.

### 6.3 Read order

For a record or a query, the client tries, in order:

1. The local index.
2. Entries from retained slices. Bodies come from the named provider or the origin.
3. A live query to selected peer providers.
4. The author's homeservers: the active one (section 7.4), then the rest of the route in order.
5. The preferred large indexer.
6. Alternate large indexers.

The client returns local hits before any network call. It moves outward only while the request is unsatisfied: a record is missing or older than the freshness window, or a query's scope was not covered. It skips a provider whose health is failed for that role and scope, or whose privacy class does not allow the request. Indexer bytes enter the replica as the author's record. Anything the indexer added stays labeled as that indexer's claim.

A read from any step is checked the same way: the bytes must match the expected hash when one is known, and an entry must match its bytes.

### 6.4 Health

Health is kept per provider, per role, and per scope. A host can serve Dana's records to everyone and refuse Alice's writes.

| Observation | Action |
|---|---|
| Timeout, connection failure, retryable server error | Keep state. Mark the role and scope degraded, then failed after 3 consecutive failures. Try the next eligible provider. |
| Rate limiting | Respect the backoff. Use the next eligible provider within the privacy policy. |
| Session expiry | Refresh once through the approved mechanism. Local access continues regardless. |
| Persistent refusal or quota exhaustion | Mark the role and scope refused. Use an already enrolled alternate. Never create a paid account silently. |
| Missing known record or incomplete answer | Try the next source. Never infer an author deletion from an omission. |
| Bad signature, unexpected signer, hash mismatch | Quarantine the response. Try another carrier without lowering the evidence requirement. |
| Every path down | Keep working locally. Keep pending fetches and publications. |

A failed provider cools down for 1 minute, doubling to 30 minutes, with jitter. After the cooldown, one probe decides whether it returns to healthy. The client never waits on a known failed provider before showing local data. These values are starting points to measure.

### 6.5 Replaceability

| Role | Default today | Replaced by | Switch |
|---|---|---|---|
| Broad search and feeds | Synonym's Nexus | The local index, retained slices, any provider with `query`, another indexer | Automatic, by read order and health |
| Reading another key's records | That key's homeserver | Its other enrolled homeservers, its mirrors, peers that hold it, slices | Automatic |
| Publishing the user's records | The primary homeserver, often Synonym's | A pre-enrolled alternate, chosen by the failover key | Automatic within the enrolled set. Enrollment uses Ring once. |
| Notices to the user | The first notice provider in the route | The other listed notice providers. Peers' `refs` answers. | Automatic, on the sender's side |
| Finding providers | The shipped defaults | Routes of familiar keys, advertisements, `peers`, slices | Automatic within budget |
| Identity resolution | A PKARR relay | Other relays, or the DHT directly | Automatic, in the SDK |
| Media | The author's homeserver | Any holder. The hash decides. | Automatic |
| App code | The web origin that served the app | The installed app runs offline. A new install from another origin needs a workspace import. | Manual for a new install |

Synonym runs the default for several roles because it runs them today. No role requires Synonym.

## 7. Publishing and failover

### 7.1 Outbox

An outbox row holds a local operation id, account, target URI, intended bytes, dependency ids, known base version, and a state per destination: `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, or `conflicted`. Persist the row and the bytes before the interface reports local success. The homeserver's acknowledgment is the publication receipt. An indexer's acknowledgment is not. A retry may repeat a source event for the same bytes. The client deduplicates what it shows and MUST NOT promise that the server ran the operation once.

Logout and an explicit wipe are user actions. A network failure is not.

### 7.2 Route and enrollment

An identity publishes a route, `slime-route/1`, at `pubky://<identity>/pub/slime/route.json` on every enrolled homeserver:

| Field | Meaning |
|---|---|
| `identity` | The identity key. |
| `sequence`, `issued_at` | Version and time. |
| `homeservers` | Enrolled homeserver keys, in order of preference. At most 8. |
| `failover` | The failover key and its `expires_at`. |
| `notice` | Notice provider keys. At most 8. |
| `mirrors` | Provider keys that retain the identity's authored public records. |
| `providers` | Provider keys the identity operates. |

The route is authenticated by a pin in the identity's own PKARR packet, a TXT record named `_slime`:

```text
v=slime1 rt=<sha256 hex of route.json>
```

A route whose hash does not match the pin is a lead, never an authority. A hostile homeserver cannot substitute one.

Enrollment happens once, through Pubky Ring:

1. The user picks at least one alternate homeserver, preferably from a different operator.
2. Ring signs the user up on each and authorizes the designated publisher (the device or companion that publishes for this account) with a session on each.
3. The designated publisher generates the failover key and gives Ring only its public key.
4. Ring adds the `_slime` pin to the identity's PKARR packet and keeps the existing `_pubky` record. The route is written to every enrolled homeserver.

Ring and the SDK MUST preserve the `_slime` record whenever they republish the identity's packet. The identity seed stays in Ring throughout.

### 7.3 Replication

The designated publisher writes every authored public record to every enrolled homeserver, and tracks acceptance per destination. Repair runs from the device or companion that holds the bytes. It never runs by asking a failed primary to push. Private data never goes to a public homeserver copy. An encrypted private backup goes to its own destination.

### 7.4 Automatic switch

The designated publisher switches the active homeserver when the current one:

- refuses the user's writes after a session refresh (authorization rejected, account suspended, quota exhausted), confirmed by one retry, or
- fails 3 times across at least 10 minutes.

It picks the next enrolled homeserver in route order whose `publish` health is good and whose replicated copy has verified. It writes the pending operations there. Then it publishes a new PKARR packet for the failover key, signed by the failover key, with a TXT record named `_slime`:

```text
v=slime1 id=<identity key> home=<homeserver key> seq=<n> rt=<route hash>
```

`seq` increases with every switch. Any client that holds the signed packet MAY republish it unchanged.

A Slime reader resolves an identity like this:

1. Resolve the identity's PKARR packet. Read `_pubky` and the `_slime` pin.
2. Obtain the route from any enrolled homeserver, mirror, peer, or folder, and check it against the pin.
3. Resolve the failover key's PKARR packet. Accept its `_slime` record only if the failover key is the one the route names, `id` is the identity, `rt` matches the pin, `home` is an enrolled homeserver, the route's `expires_at` has not passed, and `seq` is higher than any the reader has already accepted.
4. Read from the accepted `home`. Without an acceptable failover record, read the route's homeservers in order.

Switching back to the primary follows the same rules. It happens only after the primary passes write and read checks for 24 hours, or when the user chooses it.

The failover key can only choose among homeservers the identity already enrolled. It cannot sign records, grant sessions, change the identity's PKARR packet, or add a homeserver. It expires. Ring revokes it by publishing a route without it. A stolen failover key can move the active home among the user's own enrolled homeservers, each of which already holds the user's records.

A client that does not implement Slime reads only `_pubky`, which still names the old primary. The designated publisher queues a request for Ring to move `_pubky` to the new home. Until Ring signs it, the app shows that the public address for other clients has not moved.

### 7.5 Mutable edits

New records with unique paths publish automatically on any enrolled homeserver. An edit or a delete of a mutable path is different. Until the homeserver has a tested conditional write, the client MUST NOT replay an edit or a delete onto a mutable path after a disconnect or a switch. It keeps the pending change as `conflicted` and asks the user to rebase. A GET followed by a PUT is not a conditional write.

The conditional write the homeserver needs is:

```text
apply(operation_id, origin, expected_version_or_absent, action, body)
```

The same operation id returns the same outcome. A version mismatch conflicts and does not write. A delete leaves enough history that an older queued PUT cannot bring the object back. A returning homeserver with stale edits does not overwrite an accepted successor.

## 8. Folders

A set is a directory. ZIP, HTTP, and removable media carry the same directory.

```text
<set>/
    README.md
    keys.txt
    links.txt
    records/<author-key>/<path under that key>
    media/
    history/
    proofs/
    providers/
    slice.json
    set.json
    set.sig.json
```

`README.md` SHOULD be present. `keys.txt`, when present, has one canonical z-base-32 public key per line. `links.txt`, when present, has one URI per line. A line whose first non-whitespace character is `#` is a comment. Importers MAY trim ASCII whitespace on list lines. They MUST NOT rewrite a file whose digest is being checked. `providers/` holds advertisements and their signatures. `slice.json` makes the set an index slice (section 4.2).

Under `records/<author>/`, the path is the claimed origin. That claim is the exporter's until the reader accepts the source or an author proof checks out. If the path is ambiguous, the importer MUST NOT guess from the file contents. When a source path is unsafe as a filename, the exporter MUST use a generated safe name and an `origin` field in `set.json`. It MUST NOT change the logical URI quietly.

The README SHOULD say what was selected. Clients MUST render it with scripts, remote embeds, and active HTML disabled. README text MUST NOT change follows, trust, budgets, signing, or serving, and MUST NOT start a tool.

### 8.1 Inventory and signature

`set.json` is format `slime-set/1`. It lists every payload file once, in ascending ASCII path order, with the exact byte length and lowercase hex SHA-256. The only root files left off the list are `set.json` and `set.sig.json`. Optional `origin` MUST match a recognized record path. Optional `created_at` is the exporter's UTC time, not the author's. Optional `previous` is `sha256:<digest>` of an earlier `set.json` from this exporter. It does not edit the authors' records and it does not delete anything.

Verifiers hash the exact `set.json` bytes they received. They MUST NOT parse and re-serialize before hashing. Duplicate keys, invalid UTF-8, a leading byte-order mark, non-finite numbers, and unknown fields in a version-1 object MUST be rejected.

Signatures use `slime-signature/1` with algorithm `Ed25519` and a purpose: `set`, `record`, or `provider`. The signed message is the ASCII bytes of `slime/<purpose>/1`, one zero byte, then the 32-byte SHA-256 of the exact signed file. The signature is 64 bytes, unpadded base64url. The `signer` field is a canonical Pubky public key. A signature for one purpose MUST NOT be accepted for another.

A `set` signature means this key committed to this inventory. It MUST NOT be accepted as authorship of a record, a session grant, a PKARR update, or a payment. A person signing a set with an identity key MUST use an isolated signer such as Pubky Ring. The tool MUST NOT ask for a mnemonic or put an identity seed in the archive, the page, or a peer process. A homeserver access grant MUST NOT be used as a content-signing key. A provider signs its slices and advertisements with its provider key, which is shown as that key.

A bad advertised signature MUST quarantine the import. It MUST NOT be accepted as an unsigned folder from a trusted sender. A valid signature with missing bodies is an authenticated inventory, not a complete set. Files absent from the inventory MUST NOT enter a verified set.

Version-1 names use ASCII letters, digits, `_`, `-`, `.`, and `/`. Each segment is 1 to 128 bytes. The full relative path is at most 512 bytes. Reject absolute paths, empty segments, `.` and `..`, backslashes, control characters, drive prefixes, percent-decoding, segments that end in a dot, Windows device names, and names that collide if case is ignored. Reject archive links, device entries, and duplicate names. Stage the archive before activating it. Never extract into the live account directory.

Parsing ceilings: `set.json` and `slice.json` 16 MiB and 100,000 entries, a query response 4 MiB and 1,000 entries, an advertisement or route 64 KiB, a notice or signature file 8 KiB. A client MAY set a lower budget and MUST fail in the open when it does.

### 8.2 Import

Import is staged and idempotent. It MUST NOT publish under the receiver's key, follow imported keys, pay, or change policy. Importing a folder MUST NOT add its authors to the shared scope. Importing the same bytes again MUST NOT create a second post, follow, or tag. Store original bytes before building any normalized view. An advertisement found in a folder is a lead until the user's policy admits its provider.

## 9. Merge

Evidence accumulates. The current view is a projection under the reader's rules.

| Question | Answered by |
|---|---|
| Are these the bytes? | A hash |
| Did this exporter ship this selection? | A set signature, or trust in the supplier |
| Did this author commit to these bytes? | An author proof, checked under its own rules |
| Did this supplier report seeing this version? | A source observation or an entry |
| Is this version current? | The reader's admitted sources, not the newest ZIP and not the export time |

An old valid signature does not freeze a record as current. Export time does not make a record newer. Two conflicting author statements both stay until an admitted successor or an explicit choice. A gap in a proof chain stays a gap. An unsupported proof stays opaque and MUST NOT show a verification badge.

The same evidence and the same policy SHOULD produce the same projection. Readers do not have to agree with each other.

## 10. Commerce and disclosure

Public listings and private activity use the same folder rules and the same merge rules. Slime defines no listing schema and no marketplace enrollment. An adapter projects the shop, listing, review, and tag records that are actually deployed.

| Class | Examples | Default |
|---|---|---|
| Public | Seller profile, shops, listings and their offer terms, selected images, tags, reviews, public follows, public bookmarks | Shared when the seller or author is familiar. Exportable when the user selects them. |
| Personal | Searches, filters, private favorites, private follows of shops and listings, drafts, notes, trust marks | Stay local. A private favorite or private follow fetches the public records and does not itself leave the device. |
| Transaction | Inquiries, buyer offers and bids, orders, addresses, invoices, payment requests, receipts, messages | Paykit, the transaction service, or an encrypted backup the user chose. Never a public set. |

Duplicates merge on native identity and retained version. Title, image, price, and product code MUST NOT merge two sellers' stock. Copying a listing MUST NOT add quantity. An admitted withdrawal MUST NOT lose to an older catalog. Price stays in its native unit. Floating-point rounding MUST NOT authorize a total.

Local search and retained images, with the network quiet, MUST NOT open sockets. That includes analytics and remote images.

A contact link or a payment link is a hint. Starting Paykit, or opening a Lock, is a separate action against the live counterparty. An offline catalog MUST NOT reserve inventory or guarantee a price. A signature on a tag or review is not proof of purchase and not proof the claim is true.

## 11. What the interface shows

The user MUST be able to inspect, for any record, its origin, supplier, proof status, dependency state, and the scope that was consulted. For the account, the interface shows local retention, acceptance per homeserver, and indexer visibility as separate facts. There is no single synced flag. When a role is degraded, it shows which role, which provider took over, and whether other clients can still find the user's public address.

An empty result means no match in the scope that was consulted. A signature MUST NOT be labeled as completeness, clock accuracy, current stock, or truth. An unknown global count MUST NOT be shown as zero.

## 12. What Slime does not do

- No global index in the DHT. PKARR carries only per-key pointers, each signed by its own key.
- No consensus about index contents, no shared ranking, and no universal reputation score. Providers return candidates. Each reader ranks locally.
- No flooding gossip. References are followed one hop at a time, within a budget.
- No broadcast of searches and no forwarding of queries.
- No duty to store strangers' data. Providers choose their scopes.
- No mandatory torrent client, blockchain, or token.
- No new messaging. A notice is a pointer to a public record.
- No homeserver process inside the browser.
- No new encryption format. Confidential delivery uses an existing authenticated channel.
- No identity seed outside Ring, and no change to the identity's PKARR packet by the app.
- No offline global inventory, fulfillment, or seller reputation score.

## 13. Acceptance

**Exchange** is met by the folder, signature, slice, merge, commerce-disclosure, and hostile-archive checks in [examples/](examples/README.md), ported into the App.

**Provider** is met when an independent implementation serves a signed advertisement, answers the four primitives deterministically within its declared scope, returns original bytes by hash, and accepts, checks, and indexes notices.

**Replica** is met by the headline test above, run with real clients and independently operated services, after the phase gates in the [development plan](development-plan.md): offline boot, outbox survival, a local index that answers before any network call, familiar-scope collection with dependencies, automatic replacement of every read role, slice and live-query discovery, notices from unknown keys, and publishing failover within the enrolled set.
