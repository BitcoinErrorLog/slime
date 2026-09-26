# Slime specification

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **Replaceable, verifiable indexing.** Several independent indexers provide discovery and search, and any of them can be replaced. Every record carries its author's signature, so every copy and every indexer answer can be checked. Anyone can also publish a signed slice of what they keep, the smallest indexer there is. Indexers do search. Slices do not.
2. **Local fallback.** When an indexer or a homeserver is disrupted or refuses service, the app keeps working from local state and replaceable providers. Reading, search over what is retained, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable. Synonym's Nexus and Synonym's homeserver are defaults, not dependencies.

**Headline test.** Alice, Bob, and Carol use Pubky App on Synonym's homeserver. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely, and Alice's app fails over to a second indexer that Synonym does not run. Then Dana's homeserver goes dark. Alice still opens Dana's shop, listings, and tags, because Bob's slice and the indexer both hold them and every copy carries Dana's signature, and she searches them offline. A forged copy of one listing, with a different price, is rejected rather than shown. Carol tags a listing, and Alice finds the tag through the indexer. Then Synonym's homeserver stops accepting Alice's writes while still serving stale reads. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, readers find it through the homeservers her PKARR record lists, and her edits follow her signed home statement. Alice's identity seed never leaves Pubky Ring.

Every rule below serves one of the two jobs or protects a boundary between them. The [development plan](development-plan.md) ends on the headline test and its harder variants (section 13).

Requirements use MUST, SHOULD, and MAY.

## Terms

- **Homeserver.** The host that stores a key's records.
- **[PKARR](https://github.com/pubky/pkarr).** Signed DNS records on the Mainline DHT. Each identity key signs its own packet. Its `_pubky` records say which homeservers hold the key's data.
- **Identity key.** A user's PKARR key. Its seed stays in Pubky Ring.
- **Enrolled homeservers.** The homeservers named by the `_pubky` records in the identity's PKARR packet, in priority order.
- **Grant.** A `pubky-grant`: a JWS the identity key signs through Ring, binding an app's client key to capabilities and an expiry. Pubky apps use grants to get homeserver sessions.
- **App key.** The client key of the grant an app writes with.
- **Author signature.** The app key's signature over a record, made at write time. It proves that a key the author granted wrote these bytes.
- **Content hash.** BLAKE3 of a record's exact bytes, in standard base64: the value the homeserver returns as the ETag and as `content_hash` in its event stream.
- **Replica.** The device's copy of original bytes, local work, provenance, and a derived index. The app renders from it.
- **Entry.** One line of an index: a record URI, its kind, its content hash, what it references, and its author signature.
- **Indexer.** A service that reads many homeservers' event streams and answers discovery and search. Nexus is one.
- **Sharing choices.** The user's share and don't-share settings for keys, tags, shops, listings, domains, and record kinds.
- **Slice.** A static, signed export of the records a user's sharing choices select, published on the user's own homeserver.
- **Services document.** An identity's mirrors, published through its own homeserver session.
- **Failover key.** The client key of the designated publisher's grant.
- **Home statement.** The failover key's signed statement of which enrolled homeserver decides the identity's mutable paths.
- **Familiar scope.** The public records a device collects and keeps (section 3.1).

Slime writes its own documents under `/pub/slime/`.

Three conformance levels:

- **Exchange.** Import and export folders and slices. Verify inventories, author signatures, and signatures on Slime documents. Follow the merge and disclosure rules.
- **Replica.** Exchange, plus a durable workspace, a local index built from originals, the replica interface, familiar-scope collection with dependencies, sharing controls, an ordered indexer list with automatic failover, and publishing failover once enrolled. This is the Pubky App target.
- **Indexer.** Serve signed answers to the four primitives of section 4.4, with author signatures on every entry.

A client MUST say which levels it implements.

## 1. Coverage

This matrix is the scope of Slime. Each row says how a data type serves job 1 (indexed, and shared when a user's sharing choices include it), how it serves job 2 (retained locally, and what happens when a provider fails), and where its privacy boundary sits. A data type that is not in this matrix is outside Slime.

| Data type | Indexed and shared (job 1) | Retained locally (job 2) | When a provider fails (job 2) | Privacy boundary |
|---|---|---|---|---|
| Profiles | Entry kind `profile`, with its image and links in `refs`. | Own profile, familiar keys, and the author of every retained record, as a dependency. | Renders from the replica. Refreshes from the key's enrolled homeservers, indexers, and slices. | Public record only. |
| Posts | Kind `post`. Parent, embed, attachments, and links in the text go in `refs` (section 4.1). | Own posts, familiar keys' posts, and posts the user opened. | The following feed is built locally from retained authors. Composing goes to the outbox. | An opened post is kept. It is shared only if the user's choices include it. |
| Replies | Kind `post` with the parent in `refs`. Indexers answer `refs(parent, kind=post)`. | Replies to own posts, replies in retained threads, and each reply's parent as a dependency. | Replies from unknown keys arrive through indexers. | Public records only. |
| Follows | Kind `follow`, with the followed key in `refs`. Indexers answer followers with `refs(pubky://K/, kind=follow)`. | Own follows, which define the familiar keys. Familiar keys' follows, for trust paths. | The graph is local. New followers arrive through indexers. | Public follows can be shared. A local trust mark is never offered for sharing. |
| Mutes | Kind `mute`, with the muted key in `refs`. | Own mutes, and familiar keys' mutes as filter input. | Filters run locally. | Public mute records only. A local hide list stays local. |
| Tags | Kind `tag`, with `label` and the target in `refs`. Indexers answer `label` and `refs(target, kind=tag)`. | Own tags, tags by familiar keys, and tags whose target is retained. | Tag lookups run locally. New tags arrive through indexers and slices. | A tag stays a claim by its author. Sharing it is not agreeing with it. |
| Bookmarks and favorites | A public bookmark is kind `bookmark`, with the target in `refs`. A private favorite is never an entry. | Both. Either one pins the target and its dependencies. | Bookmarked and favorited items open offline. | A private favorite is never offered for sharing, exported, or answered for. |
| Custom feeds | Kind `feed` for a published feed definition. | Own feed definitions. Feeds are evaluated locally over the replica. | A feed runs offline and shows what it consulted. | Public definitions only. Searches stay local. |
| Shops | A shop is a seller's key and the public records the seller publishes under it. Slime needs no shop schema. Indexers answer `author(seller)`. | Every public record of a followed seller, and of the seller behind a followed or favorited listing, with the seller profile and media within budget. | The shop renders from the replica. While the seller's homeserver is down, author-signed copies come from indexers and slices. | Public records only. |
| Listings | Ordinary records under the seller's key, such as posts with attached files. `refs(listing)` finds tags and bookmarks on a listing. | Every public record of a followed shop, and every followed or favorited listing, with images within budget. | Search over retained listings runs offline. A copy without the seller's signature is rejected. Retained listings show when they were retrieved. | Public records only. A copy reserves nothing. |
| Offers | Public offer terms are fields in the seller's own records. Buyer offers, bids, and counter-offers are never shared. | Terms, with the seller's records. The user's own offers stay in the workspace or with the transaction service. | Making an offer needs the live seller through Paykit. It queues and is not shown as sent until the seller's side accepts it. | Buyer offers are transaction data. |
| Reviews | Public records by other keys that reference a listing or seller. `refs(listing)` finds them. | Reviews on retained shops and listings. | Read locally. New reviews arrive through indexers. | A review is its author's claim. An attestation is checked under its own rules. |
| Followed shops and followed listings | Public form: a follow of the seller's key, or a public bookmark of the listing. Private form: nothing leaves the device. | Both forms pin every public record of the seller, the seller profile, tags and reviews on them, and media within budget. | Browsing and search work offline. Updates come from indexers and slices that hold author-signed copies. | A private follow follows the favorite rules. Following a shop does not by itself share it. |
| Blobs, media, and other dependencies | Kinds `file` and `blob`. A post reaches its image through a file record whose `src` names the blob. Blobs carry author signatures like any record. | Tracked per record as retained, missing, fetchable, or withheld (section 2.4). Text first, media within budget. | A missing image shows as missing. Network-quiet mode does not fetch it. | Locked bytes are withheld. Private uploads stay private. |
| Slices | A static export signed by the publisher's key. Every record in it carries its author signature. Published on the publisher's homeserver and mirrored by anyone. | Imported slices merge into the replica, with the publisher recorded as supplier. | A retained slice answers locally with no witness. | Exactly what the choices select, and public entries only. |
| Signed indexer answers, services documents, and home statements | Indexer answers and home statements are signed by grant keys and carry their grants. Services documents and home statements live on the identity's enrolled homeservers. | The ordered indexer list with health, and each followed identity's enrolled homeservers and home. | Cached copies keep routing working while a homeserver is down. | Public by design. They state answers and locations, never the user's queries. |
| Author signatures and history | Every record in a folder, slice, or indexer answer carries its author signature and the grant behind it. Earlier versions travel with their own signatures. | Kept in the record store with each retained version. | Verification runs offline. | The signer's key is visible. An identity key signs only through Ring. |
| Last-read marker | Never shared. `/pub/pubky.app/last_read` is not an entry kind, and slices, folders, and answers never carry it. | The user's own marker. | Read and updated locally. | The App stores it at a public path today, so anyone can read it from the homeserver. Moving it under `/priv/` in `pubky-app-specs` closes that. |
| Private workspace | Never offered for sharing. | Drafts, outbox, local read state, searches, carts, notes, and trust marks. | Compose and queue offline. | Never in folders, slices, or answers. An encrypted backup goes only to a destination the user chose. |
| Transactions | Never offered for sharing. | Held by Paykit, the transaction service, or an encrypted backup the user chose. | Queued until the live counterparty answers. | Inquiries, buyer offers and bids, orders, addresses, invoices, payment requests, receipts, and messages never enter a public set. |
| Locked content | Only the public preview fields the seller publishes. | Unlocked bytes stay in the workspace under the Lock's terms. | Unlocking needs the live Lock. | Locked bytes are never offered for sharing, served, or exported. |

Entry kinds follow the record types in `pubky-app-specs`: `profile`, `post`, `follow`, `mute`, `tag`, `bookmark`, `feed`, `file`, and `blob`. The last-read marker is recognized and never becomes an entry. Every other record, including whatever records a seller uses for a shop, listing, or review, is kind `other`. Slime retains, shares, and indexes an `other` record by its URI, its author, and the references in its bytes, with no schema.

## 2. The replica

### 2.1 Records and author signatures

A logical record is `pubky://<author>/<path>`, checked with the existing SDK. The author key is not the homeserver hostname and not the key of whoever supplied the copy.

A retained version is the origin URI plus the content hash. A replica matches an event from the homeserver's event stream to a retained version by that hash, and revalidates with `If-None-Match` against the ETag, without downloading again. Record ids follow `pubky-app-specs`: tag, bookmark, and blob ids are its BLAKE3-derived HashIds, and post and file ids are its TimestampIds.

Every record carries an **author signature**. The app writing the record signs the record's URI, its content hash, and the signing time with its app key, and the homeserver stores the signature and the app's grant and returns them with the record on GET and in the event stream. A reader verifies offline:

- the signature verifies under the key it names,
- that key is the grant's client key (`cnf`),
- the grant's issuer (`iss`) is the record's author,
- the grant's capabilities allow writing the record's path, and
- the signing time falls within the grant's validity.

A record outlives its grant: the signature stays valid after the grant's `exp`. The encoding follows the delegated-key design adopted in `pubky/pubky-homeserver` and the SDK. The reference fixtures use a provisional JWS encoding of the same claims. A bearer session token MUST NOT sign content. A grant client key signs only what its capabilities allow.

A copy from anyone other than the author's own homeserver (an indexer, a slice, a folder, a mirror) is admitted only with a valid author signature. An unsigned or badly signed copy is rejected. It is never ranked or shown as a version. Bytes read from the author's own homeserver carry that homeserver's session authority. Readers cannot see a grant's revocation (section 7.2), so a revoked key's earlier signatures still verify.

Three stores, even when one database holds them:

| Store | Holds | Rule |
|---|---|---|
| Workspace | Drafts, outbox, local read state, private settings, sharing choices, trust marks, favorites, carts, orders | Session failure MUST NOT erase it. It is not a cache. It MUST NOT live in a database the app deletes or recreates on a schema change. |
| Record store | Original bytes, author signatures and grants, origins, suppliers, deletion evidence | Normalization MUST NOT rewrite these bytes. |
| Derived index | Entries, feeds, tag lookups, local search | Rebuildable from the record store. An indexer's counts and scores stay labeled as that indexer's claims. |

An app whose local database is a cache that is recreated on a version change keeps the workspace and record store in a separate database outside that recreate path.

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
  query(op, args, cursor)    the primitives of section 4.4, over retained entries
```

`putLocal` and `deleteLocal` record intent. They MUST NOT report that a homeserver accepted anything. A record under another key MAY be retained. It MUST NOT be edited or deleted locally as if the reader authored it. `query` uses the same four primitives and the same ordering as an indexer, so a slice, a signed answer, and the local index are interchangeable inputs.

Four absences stay distinct: the source is unavailable, the client has not looked, the source reports the record gone, and a deletion in the author's event stream. An indexer's omission is never an author deletion. Dropping a record from a personal scope is a retention choice, not an author deletion.


### 2.3 Sync architecture

```text
            +--------------------------- Replica ---------------------------+
            |  workspace  |  record store  |  derived index                 |
            |  outbox, cursors, provenance, indexer list, health            |
            +-------------------------------+-------------------------------+
                                            |
        +-----------------------------------+-----------------------------------+
        |                                   |                                   |
  Homeserver sync                       Indexer sync                      Slice sync
  publish own records,             discovery and search              import and publish
  replicate to enrolled            from an ordered list              static signed slices
  homeservers, follow the          of indexers, with
  event streams of familiar        failover
  keys' enrolled homeservers
```

The three loops are independent. A failed indexer does not stop publication. A failed publishing session does not stop browsing. A failed media source does not invalidate a text record.

The homeserver loop reads each familiar key's event streams (`PUT` and `DEL` with a cursor and `content_hash`) from every enrolled homeserver of that key, and takes their union for new records. One event-stream request covers at most 50 users, so the loop batches familiar keys by homeserver in groups of 50. Each adapter keeps its own cursor, bound to that source and that scope. A cursor MUST NOT be reused between sources, or after a suspected reset. Persist the event, and any pending body fetch, before moving the cursor forward. A body whose content hash differs from its event's is a newer version, not that event's body. Event positions and entry `seq` values that can exceed JavaScript's safe integer range MUST be stored as decimal strings.

Fetchers MUST limit URL schemes, refuse local and metadata addresses unless the user allowed them, check redirects, cap response size, and MUST NOT send one origin's credentials to another. Keys and links in an import are not permission to crawl.

### 2.4 Dependencies

A retained listing without its images is not a working shop. Each record's dependencies are the records it references (a reply's parent, a tag's target, a post's attached files, and any other `pubky://` record URI in its bytes) plus its author's profile. Dependencies chain: a post reaches its image through a file record, and the file's `src` names the blob. The replica follows the chain until a dependency is not retained. For each dependency it records one state:

| State | Meaning |
|---|---|
| `retained` | The bytes are in the record store and match the content hash. |
| `missing` | No copy is held and no holder is known. |
| `fetchable` | No copy is held. An indexer, slice, or origin is known to hold it. |
| `withheld` | Locked, private, or over the media budget. |

Text dependencies of a retained record are fetched with it. Media follows the media budget. A pinned item (an own record, a followed shop, a followed listing, a favorite) pins its dependencies within that budget. A record with a missing dependency renders with the gap shown. It MUST NOT present a missing image as a removal by the seller.

Any holder MAY serve a public dependency. The receiver MUST check the bytes against the author signature and the content hash or blob id before use. A slice that carries records SHOULD carry their public dependencies.


### 3.1 Familiar scope

A key is **familiar** when the user follows it, marks it trusted, or it is the seller behind a followed shop or listing. A trust mark is a local policy. It is not a shared record and not an endorsement.

A record is in the **familiar scope** when any of these is true:

- The user authored it.
- A familiar key authored it, and it is public.
- It is a public tag, reply, or other record that references a record the user already keeps.
- It is a public record of a seller whose shop the user follows, or a listing the user follows or favorited.

**Followed shops and followed listings** come in two forms. Following a shop is following the seller's key. Following a listing is a public bookmark of it. The private form is a workspace pin (a private favorite). Either form MUST cause the client to fetch and retain the seller's public records, the seller profile, the tags and other records that reference them, and their dependencies within budget, and to index them locally. The private form MUST NOT be exported, published in a slice, or offered as a sharing choice. The client MUST NOT add that seller to the familiar keys because of a private pin alone.

The homeserver sync loop collects the familiar scope during ordinary use, so on native clients and companions an outage is never the first time those records are fetched. In a browser, it covers what synced while a tab was open (section 12). For keys the user follows or pins, resolve their enrolled homeservers (section 7.3) and read their event streams. Group keys by host.

Starting budgets, to be measured on phones: no automatic graph expansion, 4 requests in flight, 2 per host, a 128 MiB text target, and media on demand in its own budget. Text comes before media. A phone that cannot hold its pinned scope asks for a companion. It MUST NOT evict pins.


### 3.2 Sharing controls

The app gives the user share and don't-share choices. Each choice names one of these:

| Choice | Selects |
|---|---|
| A key | That person's or seller's public records, and public records that reference them |
| All keys the user follows | The same, for each followed key |
| A shop | The seller's key, as above |
| A listing, or any single record | That record and the public records that reference it |
| A tag label | Public tags with that label |
| A link domain | Public records that link to that domain |
| A record kind | Narrows any choice above to posts, replies, follows, mutes, tags, bookmarks, feeds, files, media, or other records |

A don't-share choice removes what it names from every share choice it overlaps. The choices offer public records the device retains, and nothing else. Private favorites, private follows, trust marks, searches, the workspace, transactions, locked bytes, and the last-read marker are never offered.

The **slice** is the published result of those choices (section 4.5). It lists exactly the records the choices select. When the user changes a choice, the next slice reflects it.

## 4. Indexing (job 1)

Indexers do discovery and search: reverse edges such as followers, replies, and tags on a record live on other people's homeservers, and only a service that reads every event stream can answer them broadly. Slime makes indexers replaceable and their answers checkable. Slices add a small, static, signed export anyone can publish.

### 4.1 Entries

An entry describes one retained version:

| Field | Meaning |
|---|---|
| `seq` | The publisher's or indexer's own position counter, a decimal string. Strictly increasing within one source. |
| `uri` | The record's `pubky://<author>/pub/...` URI. |
| `kind` | One of the kinds in section 1. |
| `blake3` | The content hash. |
| `sig`, `grant` | The record's author signature and the grant behind it. |
| `refs` | Sorted URIs the record references. At most 64. |
| `label` | The tag label. Tags only. |
| `gone` | The source reports the record gone. Not an author deletion. A `gone` entry carries no hash or signature. |

`kind`, `refs`, and `label` are derived from the original bytes:

| Record | `refs` |
|---|---|
| Profile | Its image and link URLs |
| Post | Its parent, embed URI, attachments, and every http, https, and `pubky://` link in its text |
| Tag, bookmark | The target URI |
| Follow, mute | The key, as `pubky://<key>/` |
| File | Its `src` |
| Blob, feed | None |
| Any other record | Every `pubky://` record URI, bare key URI (normalized to `pubky://<key>/`), and http or https URL that is a whole string value anywhere in its JSON body |

A link in post text runs until whitespace or one of `<>"'()[]{}`, with trailing `.,;:!?` removed. Tag labels follow `pubky-app-specs`: trimmed, lowercase, 1 to 20 characters, with no comma, colon, or whitespace. A receiver that holds the bytes MUST derive the fields again and reject an entry that disagrees, MUST reject a record whose id does not match its `pubky-app-specs` rule, and MUST verify the author signature. An entry MUST NOT carry a score, rank, count, reputation, or any field not listed. The schema is `schemas/common.schema.json#/$defs/entry`.

### 4.2 Replaceable indexers

The app keeps an ordered list of indexers, not one indexer URL:

- Each indexer has a health state per request type (section 6.4). A failed indexer is skipped for its cooldown, and the next one answers.
- The shipped defaults include at least one indexer that Synonym does not run, and PKARR relays that Synonym does not run.
- For reverse-edge queries (followers, replies, tags on a record), a reader with two indexers configured MAY ask both and merge the answers, which exposes omission.
- Every record an indexer returns carries its author signature and content hash. A record without one is not admitted as the author's.
- An indexer's counts, rankings, and recommendations stay labeled as that indexer's claims.

Browsers resolve PKARR through relays only, because they cannot reach the DHT. The relay list is part of the same replaceable configuration.

### 4.3 Witnesses

A signature from a publisher or an indexer means "I saw this". It never means "the author wrote this". Only the author signature says that. Witnesses are useful once records are author-signed: several witnesses that agree on a signed record, or disagree about what exists, make omission and freshness visible. A reader never uses witness agreement to choose between an author-signed version and an unsigned or forged one. The forged one is rejected first.

### 4.4 Signed indexer answers

An indexer that supports Slime answers four deterministic primitives with a signed list of candidates:

| Operation | Parameters | Returns entries whose |
|---|---|---|
| `author` | `key`, optional `kind` | URI is under that key |
| `label` | `label` | kind is `tag` with that label |
| `refs` | `uri`, optional `kind` | `refs` contain that URI |
| `domain` | `host` | `refs` contain an http or https link to that host |

Every operation takes an optional `after`: only entries with a greater `seq`. An answer is `slime-candidates/1`. It names the `indexer` key, the `operator` identity, and the operator's `grant` for the indexer key. It echoes the `query`, gives `as_of`, lists `entries` in ascending `seq` order, and says whether it is `complete`. `complete` is the indexer's claim, never a guarantee. The answer is signed by the indexer key (section 8.1, type `slime-answer`). A reader checks the signature, the grant with the operator as issuer, that every entry matches the query, and every entry's author signature. The same query against the same indexer state SHOULD return the same answer.

A signed answer makes an indexer accountable: an answer that omits a record another indexer returned, or that differs between two readers, is provable. An indexer's other APIs (free-text search, feeds, counts) are outside this format and stay labeled as its claims.

### 4.5 Slices

A slice is a folder (section 8) whose `set.json` is signed by the publisher's key, with a `slice.json` in format `slime-slice/1`:

| Field | Meaning |
|---|---|
| `publisher` | The publisher key. MUST equal the set signer. |
| `grant` | The publisher identity's grant for that key, with write on `/pub/slime/`. |
| `as_of` | UTC time it was published. |
| `scopes` | The sharing choices, as scopes (below). |
| `through` | The highest `seq` it covers. |
| `entries` | Entries in strictly ascending `seq` order, every one inside a scope, every one author-signed. |

A scope is one of `{"key": K}`, `{"label": L}`, `{"host": H}`, or `{"uri": U}`, each with optional `"kinds": [...]`. A key scope covers the key's records and public records that reference the key or its records. A URI scope covers that record and public records that reference it. A label scope covers tags with that label. A host scope covers records that link to that host. Don't-share choices remove entries inside them.

An entries-only slice lists entries. A slice with records also carries the records under `records/<author>/<path>`. Every record body in it MUST have an entry with the same URI and content hash. The next slice from the same publisher names the previous one in `set.json` `previous`. A slice lives at `pubky://<publisher>/pub/slime/slices/<n>/`, and anyone MAY mirror it. A torrent MAY carry a snapshot. Nothing requires one.

A slice does three things an indexer query does not: it answers without anyone seeing the question, it lets a user or community with no server publish an index of what they keep, and it hands followers verified copies of a followed scope when the author's homeserver and the indexers are down. It does not do discovery. It covers only what its publisher chose to share.

### 4.6 Witnesses of the user's questions

Each step outward adds a witness to what the user is looking for. Local answers come first: the local index, then retained slices. A query to an indexer names only what the user asked. A client MUST NOT broadcast a search. A query marked private MUST NOT reach a public indexer.

## 5. Deferred

These are outside the current specification. They return only once the base in the development plan is in place and someone needs them: live query providers and their advertisements, crawling providers through `peers` lists, notices from unknown senders, and home statements beyond the stale-primary case of section 7.4. Until then, inbound replies, tags, follows, and mentions from unknown keys arrive through indexers.

## 6. Routing and automatic replacement (job 2)

### 6.1 Roles

Each role is granted on its own, per provider:

| Role | What it does |
|---|---|
| `publish` | Accepts the user's own writes. A homeserver. |
| `replicate` | Holds a copy of the user's authored public records. An enrolled homeserver. |
| `read` | Serves another key's records. That key's homeservers. |
| `index` | Discovery and search. An indexer. |
| `resolve` | Resolves PKARR. A relay, or the DHT outside browsers. |
| `backup` | Holds an encrypted private backup. |

A role MUST NOT be inferred from a README, from a slice, or from a different role.

### 6.2 The provider table

The client keeps a local provider table: each provider's key or URL, operator, granted roles, privacy class (public or private), order, credential handle, cursors, and health per role and scope. It is configuration on the device, not a public registry. The user sets policy once. The client then chooses and replaces providers on its own.

### 6.3 Read order

For a record or a query, the client tries, in order:

1. The local index.
2. Entries from retained slices.
3. The author's enrolled homeservers. New records come from the union of their event streams. Mutable paths come from the homeserver the home statement names, or the first enrolled homeserver without one (section 7.4).
4. The indexers, in the user's order, with failover.

Discovery and search go to the indexers directly after the local index. The client returns local hits before any network call, and moves outward only while the request is unsatisfied. Every copy from step 2 or 4 is admitted only with a valid author signature.

### 6.4 Health

Health is kept per provider, per role, and per scope. A host can serve Dana's records to everyone and refuse Alice's writes.

| Observation | Action |
|---|---|
| Timeout, connection failure, retryable server error | Keep state. Mark the role and scope degraded, then failed after 3 consecutive failures. Try the next eligible provider. |
| Rate limiting | Respect the backoff. Use the next eligible provider within the privacy policy. |
| Session expiry | Refresh once through the approved mechanism. Local access continues regardless. |
| Persistent refusal or quota exhaustion | Mark the role and scope refused. Use an already enrolled alternate. Never create a paid account silently. |
| Missing known record or incomplete answer | Try the next source. Never infer an author deletion from an omission. |
| Bad signature, unexpected signer, invalid grant, hash mismatch | Quarantine the response. Try another carrier without lowering the evidence requirement. |
| Every path down | Keep working locally. Keep pending fetches and publications. |

A failed provider cools down for 1 minute, doubling to 30 minutes, with jitter. After the cooldown, one probe decides whether it returns to healthy. The client never waits on a known failed provider before showing local data. These values are starting points to measure.


### 6.5 Replaceability

| Role | Default today | Replaced by | Switch |
|---|---|---|---|
| Discovery and search | Synonym's Nexus | Other indexers in the list, at least one not run by Synonym | Automatic, by order and health |
| Reading another key's records | That key's first homeserver | Its other enrolled homeservers; author-signed copies from indexers and slices | Automatic |
| Publishing the user's records | The primary homeserver, often Synonym's | An enrolled alternate | Automatic within the enrolled homeservers. Enrollment uses Ring once. |
| Keeping the user's PKARR packet alive | The primary homeserver's republisher | The designated publisher, mirrors, and every enrolled homeserver republishing the same signed packet | Automatic |
| Identity resolution | A PKARR relay | Other relays in the list, or the DHT outside browsers | Automatic, in the SDK |
| Media | The author's homeserver | Any holder of an author-signed copy | Automatic |
| App code | The web origin that served the app | The installed app runs offline. A new install from another origin needs a workspace import. | Manual for a new install |

No role requires Synonym.

## 7. Publishing and failover

### 7.1 Outbox

An outbox row holds a local operation id, account, target URI, intended bytes and their content hash, the author signature, dependency ids, the known base version's content hash, and a state per destination: `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, or `conflicted`. Persist the row and the bytes before the interface reports local success. The homeserver's acknowledgment is the publication receipt. An indexer's acknowledgment is not.

Idempotency lives in the outbox. A retry first reads the destination's ETag: when it already equals the intended content hash, the operation is done there.

Logout and an explicit wipe are user actions. A network failure is not.

### 7.2 Keys

Slime adds no delegation mechanism. Every Slime signing key is the client key of a Pubky grant, the mechanism Ring and the homeserver use to let an app act for an identity. An app generates a client keypair and asks Ring to approve a `signin_grant` or `signup_grant` for it. Ring signs the grant with the identity key: a `pubky-grant` JWS naming the issuer (`iss`), the app's `client_id`, the capabilities (`caps`), the client public key (`cnf`), a grant id (`jti`), and an expiry (`exp`). Anyone can verify a grant offline.

| Key | Grant capabilities | Held by | Signs |
|---|---|---|---|
| App key | Write on the app's paths, such as `/pub/pubky.app/` | The app | Its records, at write time (the author signature) |
| Slice key | Write on `/pub/slime/` | The app or a companion | Its slices |
| Indexer key | Write on `/pub/slime/`, from the indexer's operator | The indexer | Its answers |
| Failover key | Write on `/pub/` | The designated publisher | Home statements |

A Slime document signed by a slice, indexer, or failover key carries its grant. A reader accepts the signature only when the grant verifies against the expected issuer, the grant's `cnf` is the signing key, the grant has not expired, and its capabilities allow writing `/pub/slime/`.

Revocation is not visible to readers. It lives on each homeserver, and only the identity's own sessions can list or revoke grants. Grants last two years by default, and grant links carry no lifetime parameter, so a revoked key's earlier signatures verify until `exp`. Readers prefer copies read from the identity's own homeservers. Ring signs grants and the identity's PKARR packet. The identity seed never leaves Ring.

### 7.3 Enrolled homeservers and enrollment

The identity's PKARR packet lists every enrolled homeserver as its own `_pubky` HTTPS or SVCB record, and the record's priority gives the user's order, as in PKARR's endpoint design. Ring signs one packet for the whole set. Two to four homeservers fit within PKARR's 1000-byte packet limit. A reader tries the enrolled homeservers in priority order, and a Slime reader also reads the others (section 6.3). This needs three changes in the Pubky SDK and homeserver: the SDK can publish several `_pubky` records, the SDK tries each in order, and a homeserver republishes a packet that lists it in any `_pubky` record.

The packet has to stay on the DHT when the primary stops republishing it. So the designated publisher and the mirrors in the services document republish the identity's last signed packet unchanged, and each enrolled homeserver republishes it too. Readers accept the newest signed packet from any carrier (a relay, the DHT, a mirror, or an enrolled homeserver), because a PKARR packet authenticates itself.

An identity publishes a services document, `slime-services/1`, at `pubky://<identity>/pub/slime/services.json`, through its own session. It lists the identity's `mirrors`: keys that retain its authored public records and republish its packet. Its authority is the homeserver's: only a session the identity granted can write there.

Enrollment happens once, through Ring:

1. The user picks one or more alternate homeservers. Homeservers require a signup token by default (`signup_mode = "token_required"`), so the user obtains one from each operator, or picks homeservers with open or paid signup.
2. For each, Ring approves a `signup_grant` for the designated publisher's client key. The homeserver creates the account, and the designated publisher gets a session there.
3. Ring signs one PKARR packet with a `_pubky` record per enrolled homeserver, in the user's order.
4. The designated publisher writes the services document to every enrolled homeserver.

The designated publisher writes every authored public record, with its author signature, to every enrolled homeserver, and tracks acceptance per destination. Repair runs from the device or companion that holds the bytes. It never runs by asking a failed primary to push. Private data never goes to a public homeserver copy.

### 7.4 Automatic switch

A new record with a unique path needs no decision: readers take the union of every enrolled homeserver's event stream, and every record carries its author signature, so an enrolled homeserver cannot add a record the author did not sign. A mutable path needs one homeserver that decides, because a primary that refuses writes can keep serving stale reads.

The designated publisher switches when the current homeserver refuses the user's writes after a session refresh (authorization rejected, account disabled, quota exhausted), confirmed by one retry, or fails 3 times across at least 10 minutes, or answers with a version older than one it accepted. It picks the next enrolled homeserver in priority order whose `publish` health is good and whose replicated copy has verified, writes the pending operations there, and signs a home statement, `slime-home/1`, with the failover key (section 8.1, type `slime-home`):

| Field | Meaning |
|---|---|
| `identity` | The identity key. |
| `home` | The deciding homeserver key. MUST be an enrolled homeserver. |
| `sequence` | Increases with every switch. |
| `issued_at` | UTC time. |
| `grant` | The failover key's grant. |

It writes the statement to `pubky://<identity>/pub/slime/home.json`, with `home.jws`, on every enrolled homeserver it can reach, and sends it to the mirrors.

A Slime reader resolves an identity by reading the `_pubky` targets of the newest packet it can find, collecting home statements from every enrolled homeserver and mirror, and accepting a statement only if its grant passes the checks in section 7.2 with the identity as issuer, `home` is an enrolled homeserver, and `sequence` is higher than any statement already accepted. Equal sequences resolve to the homeserver earlier in priority order. Mutable paths come from the accepted `home`, or from the first enrolled homeserver without one. Switching back follows the same rules, after the primary passes write and read checks for 24 hours, or when the user chooses it.

The failover key can only name homeservers the identity's own PKARR packet lists. A stolen failover key can hold mutable paths on one of them until its grant expires, so failover grants SHOULD be as short-lived as Ring allows.

### 7.5 Mutable edits

New records with unique paths publish automatically on any enrolled homeserver. An edit or a delete of a mutable path uses the homeserver's WebDAV lock on the path-addressed `/storage` route:

1. `LOCK` the path.
2. Read its ETag and compare it with the outbox row's base content hash.
3. When they match, `PUT` or `DELETE` with the lock token, then `UNLOCK`. When they differ, `UNLOCK` and keep the row as `conflicted`, and ask the user to rebase.

A lock holds on one homeserver. After a switch, the same compare runs on the new deciding homeserver, so an edit made against the old primary's version conflicts instead of overwriting. A plain GET followed by a PUT without a lock is not a conditional write. `If-Match` and `If-None-Match: *` on `PUT` and `DELETE` would make this one request per write. The homeserver does not accept entity tags in conditions yet.

The homeserver does not expose `ETag` to browsers through CORS today, so a web app cannot run this compare against another origin until it does. Until then, web apps hand mutable edits to a companion, or retry them from a native client.

## 8. Folders

A set is a directory. ZIP, HTTP, and removable media carry the same directory.

```text
<set>/
    README.md
    keys.txt
    links.txt
    records/<author-key>/<path under that key>
    history/
    slice.json
    set.json
    set.jws
```

A folder that carries records MUST have a `set.json`, because that is where each record's author signature and grant travel. `README.md` SHOULD be present. `keys.txt`, when present, has one canonical z-base-32 public key per line. `links.txt`, when present, has one URI per line. A line whose first non-whitespace character is `#` is a comment. `history/` holds earlier versions the exporter chose to include. `slice.json` makes the set a slice (section 4.5).

Under `records/<author>/`, the path is the record's origin, and its author signature binds the bytes to that origin. When a source path is unsafe as a filename, the exporter MUST use a generated safe name and an `origin` field in `set.json`. It MUST NOT change the logical URI quietly.

The README SHOULD say what was selected. Clients MUST render it with scripts, remote embeds, and active HTML disabled. README text MUST NOT change follows, trust, budgets, signing, or sharing, and MUST NOT start a tool.

### 8.1 Inventory and signatures

`set.json` is format `slime-set/1`. It lists every payload file once, in ascending ASCII path order, with the exact byte length and its content hash in field `blake3`. A record's entry also carries its `origin`, its author signature `sig`, and its `grant`. The only root files left off the list are `set.json` and `set.jws`. Optional `created_at` is the exporter's UTC time, not the author's. Optional `previous` is the content hash of an earlier `set.json` from this exporter. A set's id is the content hash of its `set.json`.

Verifiers hash the exact `set.json` bytes they received. They MUST NOT parse and re-serialize before hashing. Duplicate keys, invalid UTF-8, a leading byte-order mark, non-finite numbers, and unknown fields in a version-1 object MUST be rejected.

Signatures on Slime documents are detached JWS (RFC 7515, Appendix F) with algorithm `EdDSA`, the same JWS family as Pubky grants. The protected header holds exactly `alg`, `kid` (the signer's canonical public key), and `typ`. The signing input is the base64url header, a dot, and the base64url of the exact file bytes. The file carries `header..signature`.

| `typ` | Signs | Signer |
|---|---|---|
| `slime-set` | `set.json` | The exporter. A slice is signed by its publisher key. |
| `slime-answer` | An indexer answer | The indexer key |
| `slime-home` | A home statement | The failover key |

A signature of one type MUST NOT be accepted as another. A `slime-set` signature means this key committed to this inventory. It is not authorship: the author signature on each record is. A present but invalid set signature MUST quarantine the import.

Version-1 names use ASCII letters, digits, `_`, `-`, `.`, and `/`. Each segment is 1 to 128 bytes. The full relative path is at most 512 bytes. Reject absolute paths, empty segments, `.` and `..`, backslashes, control characters, drive prefixes, percent-decoding, segments that end in a dot, Windows device names, and names that collide if case is ignored. Reject archive links, device entries, and duplicate names. Stage the archive before activating it. Never extract into the live account directory.

Parsing ceilings: `set.json` and `slice.json` 16 MiB and 100,000 entries, an indexer answer 4 MiB and 1,000 entries, a services document 64 KiB, a home statement 16 KiB, a signature 8 KiB. A client MAY set a lower budget and MUST fail in the open when it does.

### 8.2 Import

Import is staged and idempotent. It MUST NOT publish under the receiver's key, follow imported keys, pay, or change sharing choices or policy. Importing a folder MUST NOT add anything to what the receiver shares. Importing the same bytes again MUST NOT create a second post, follow, or tag. Store original bytes before building any normalized view.


## 9. Merge

| Question | Answered by |
|---|---|
| Are these the bytes? | The content hash, or the blob id |
| Did the author write them? | The author signature |
| Did this exporter or indexer ship them? | A `slime-set` or `slime-answer` signature |
| What is the author's current version? | The author's enrolled homeservers' event streams |

Only author-signed versions count. An unsigned or badly signed copy is rejected before the merge. Within one homeserver's event stream, the latest event for a path decides: a later `PUT` replaces an earlier version, and a `DEL` removes it. A copy never overrides an event stream. When enrolled homeservers disagree about a path, the home statement's homeserver decides. When no event stream is reachable, author-signed copies stand in, and two authentic versions both stay, shown as a conflict, until a stream or an explicit choice decides. Witness agreement never decides between them.

## 10. Commerce and disclosure

Slime defines no shop, listing, or review schema and depends on none. The records a seller publishes are retained, shared, and indexed like any other Pubky record. The relationships around them use record types `pubky-app-specs` already has: following a shop is a follow of the seller's key, following a listing is a bookmark, a label on a listing is a tag, and images are files and blobs.

| Class | Examples | Handling |
|---|---|---|
| Public | Seller profile and records, offer terms in them, selected images, tags, reviews, public follows, public bookmarks | Retained when familiar. Shared when the user's choices select them. Exportable when the user selects them. |
| Personal | Searches, filters, sharing choices, private favorites, private follows of shops and listings, drafts, notes, trust marks | Stay local. A private favorite or private follow fetches the public records and does not itself leave the device. |
| Transaction | Inquiries, buyer offers and bids, orders, addresses, invoices, payment requests, receipts, messages | Paykit, the transaction service, or an encrypted backup the user chose. Never a public set. |

Duplicates merge on native identity and retained version. An app that reads listing fields MUST NOT merge two sellers' stock on title, image, price, or product code, MUST NOT add quantity when a listing is copied, and MUST NOT let an older copy override a newer version from the seller. Price stays in its native unit. Floating-point rounding MUST NOT authorize a total.

Local search and retained images, with the network quiet, MUST NOT open sockets. That includes analytics and remote images.

A contact link or a payment link is a hint. Starting Paykit, or opening a Lock, is a separate action against the live counterparty. A retained copy MUST NOT reserve inventory or guarantee a price. A signature on a tag or review is not proof of purchase and not proof the claim is true.


## 11. What the interface shows

The user MUST be able to inspect, for any record, its origin, author signature status, supplier, dependency state, and the scope that was consulted. The user MUST be able to see and change every sharing choice, and see exactly what the current slice contains. For the account, the interface shows local retention, acceptance per homeserver, and indexer visibility as separate facts. When a role is degraded, it shows which role and which provider took over.

An empty result means no match in the scope that was consulted. A signature MUST NOT be labeled as completeness, clock accuracy, current stock, or truth. An unknown global count MUST NOT be shown as zero.

## 12. Limits and threat model

**What Slime handles.** A homeserver or indexer operator that refuses service, disappears, or omits records; outages; and forged copies of records. It does not handle state seizure of servers, anonymity, or the legality of what is published. Homeservers, indexers, and relays are clearnet servers with known operators, a PKARR record lists every enrolled homeserver in public, and indexers expose public reverse edges such as followers and reviews. Privacy and compliance are separate layers that build on these primitives.

**Browser limits.** A web app:

- resolves PKARR through relays only, never the DHT;
- syncs only while a tab is open (Periodic Background Sync exists only on Chromium for installed apps);
- can lose IndexedDB in Safari after 7 days without use unless the app is on the Home Screen, so it calls `navigator.storage.persist()` and shows the result;
- cannot read the homeserver's `ETag` across origins today (section 7.5).

On web, "retained" means what synced while a tab was open. The storage rules in sections 2.1 and 3.1 are guarantees on native clients and a companion, and best effort in a browser.

**Scale.** The homeserver has no batch read, and an event-stream request covers at most 50 users. A cold sync of a large follow list (300 keys, tens of thousands of records) takes on the order of an hour in the foreground at 4 requests in flight. Slices are full snapshots with no delta format, so publishers SHOULD publish on a schedule, not on every change, and keep only the latest few.

**What slices do not do.** They do not do discovery or search, and they cover only what their publishers chose to share.

## 13. Acceptance

**Exchange** is met by the folder, author-signature, slice, merge, commerce-disclosure, and hostile-archive checks in [examples/](examples/README.md), ported into the App.

**Indexer** is met when an implementation serves signed answers to the four primitives, with the operator's grant and an author signature on every entry.

**Replica** is met by the headline test above, and by these variants, each run with real clients:

- The seller's homeserver is down, and the shop is served from author-signed copies.
- A forged listing among several copies is rejected, not shown as a version.
- The primary times out; separately, it serves stale data while refusing writes.
- A fresh install finds content through its default indexers alone.
- Every participant uses Synonym-operated homeservers.
- Nexus is down and a second indexer restores search. The mesh does not restore search, and the test says so.
- The primary stops republishing, and the identity still resolves.
