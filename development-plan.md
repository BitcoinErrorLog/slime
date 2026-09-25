# Slime development plan

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **P2P indexing.** Peers share what they already know: records, tags, follows, shops, listings, and whatever parts of their own index they choose to share. The network stays densely indexed without any single indexer, and anyone can discover it and crawl it.
2. **Local fallback.** When an indexer or a homeserver is disrupted or censored, the app keeps working from local state and replaceable providers. Reading, search, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable.

This plan builds both jobs into Pubky App and ends on one test:

> Alice, Bob, and Carol use Pubky App. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely. Alice follows Dana. Bob already retains Dana's shop, listings, and tags, has chosen to share them, and his Slime provider advertises that choice. Alice's app finds Bob's provider through her configured mesh, pulls Dana's shop, listings, and tags, builds them into her local index, and searches them offline. Carol publishes a new tag on one of Dana's listings. Alice sees it through Bob's index or a notice, with no Synonym service involved. Then Synonym's homeserver starts refusing Alice's writes. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, her public location moves to that alternate, and Bob and Carol read the post. Alice's identity seed never leaves Pubky Ring.


Each phase closes one piece of that test. The rules are in the [specification](spec.md). The data each phase must cover is the [coverage matrix](spec.md#1-coverage).

Build on the current releases: the Pubky SDK 0.13 (crate `pubky`, npm `@synonymdev/pubky`) from `pubky/pubky-homeserver`, which adds grants, path-addressed `/storage`, and WebDAV locks; `pubky-app-specs` 0.8.1 for record types; homeserver event streams; PKARR; Pubky grants for subordinate keys; Paykit; `pubky/locks`; and `pubky-backup`. Do not open a new protocol repository until a second implementation needs a shared crate. Read the current `pubky/pubky-app` sources for posts, session restore, and homeserver signup before editing.

Reference fixtures and a Python checker live in [examples/](examples/README.md). They use real pubky.app records and cover folders, signatures, slices, advertisements, query responses, notices and their flood rules, services documents, home statements, merges over event streams, and the headline test's data path. Port those vectors. They do not build the configured mesh from the network, and they do not show that the App survives a restart, that Ring signs a grant, or that a homeserver accepts a write. Those gates need real clients.

## Phase 0. Durable workspace

**Job:** local fallback. **Repo:** `pubky/pubky-app`

pubky-app's local database is a cache. ADR-0003 (streams as caches) and ADR-0019 (Dexie recreate on version mismatch, accepted 2026-09-15) delete and rebuild it on any schema change. The workspace and the outbox cannot live there. Open the phase with a pubky-app ADR that keeps the workspace and record store in a separate IndexedDB database, outside the recreate path, with its own versioned migrations. It amends ADR-0001 (local-first writes): a local write lands in the workspace first and the cache is filled from it.

An outbox row has a local operation id, account, target URI, intended bytes and their content hash, dependency ids, the base version's content hash, and a state per destination: `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, or `conflicted`. Persist the row and the bytes before the interface reports local success. If the homeserver throws, keep the row. Do not delete the local post.

Ship a private workspace export in this phase. It is a file the user saves, not a public set.

**Gate:** cold start of the installed app with no network and with session refresh failing. Retained data reads. Kill the process after queueing a post and find it after restart. Expire the session while offline and keep the work. Bump the cache's schema version so ADR-0019 recreates it, and lose nothing in the workspace or outbox.

**Stop if:** the fix needs the identity seed in the page. That belongs in Ring.

## Phase 1. The replica and its local index

**Job:** both. **Repos:** `pubky-app`, `pubky-app-specs`

Store original bytes by origin URI and content hash (BLAKE3, as the homeserver's ETag and event `content_hash`). Implement the replica interface: `get`, `list`, `putLocal`, `deleteLocal`, `events`, `versions`, `dependencies`, and `query`. The app renders from it.

Write one adapter per `pubky-app-specs` record type (profile, post, follow, mute, tag, bookmark, feed, file, blob) that turns a record into an entry and checks its id. Recognize `last_read` and never turn it into an entry. Every other record, including whatever a seller publishes for a shop or listing, becomes kind `other`, with refs taken from the `pubky://` and http URIs in its body. Posts also take refs from links in their text. Slime does not wait on, or depend on, any shop or listing schema.

Implement the four primitives (`author`, `label`, `refs`, `domain`, each with `after`) over retained entries. The following feed lists retained authors' posts. It is not a saved list of indexer ids. An indexer response enters the record store only after the original fields are taken out. Anything the indexer added stays labeled as its claim.

**Gate:** rebuild the index with the network blocked and recover the following feed, tags, known replies, followers already seen, and every retained record of followed sellers. The ported vectors return the same answers, including refs from post text and from records of unknown type. An entry that disagrees with its bytes is rejected, and so is a record whose id breaks its `pubky-app-specs` rule. A body whose hash differs from its event's is kept as a newer version.

## Phase 2. Familiar scope, followed shops, and dependencies

**Job:** both. **Repos:** `pubky-app`, the SDK in `pubky/pubky-homeserver`, `paykit-rs`, `pubky/locks`

Collect the familiar scope during ordinary use: follows, trust marks, and the sellers behind followed shops and listings. Read each key's event streams, group keys by homeserver, and keep one cursor per provider and scope. Persist the event before advancing the cursor. Reconcile after a suspected reset.

Following a shop is a follow of the seller's key. Following a listing is a public bookmark. A private follow or favorite is a workspace pin. All of them retain every public record of the seller, the seller profile, the tags and other records that reference them, and their media within budget.

Track dependencies per record as `retained`, `missing`, `fetchable`, or `withheld`, including the author's profile, and follow chains such as post to file to blob. Fetch text dependencies with the record. Media follows its own budget. Start with 4 requests in flight, 2 per host, a 128 MiB text target, and no automatic graph expansion, then measure.

Buy hands the seller and the record reference to Paykit, which checks the live counterparty. A Lock applies only when the record is access-gated. A retained copy does not reserve stock or override a newer version in the seller's event stream.

**Gate:** with every large indexer blocked, familiar keys refresh from their homeservers. A followed shop, public or private, browses and searches offline with its images. A listing whose image was never fetched shows the gap, not a removal. A packet capture while browsing retained shops offline shows no sockets, no analytics, no remote images, and no quote request. No outgoing request names a privately followed shop. A known record missing from an index response is not shown as deleted.

Time fixtures of 50, 250, and 2,500 familiar keys on a phone. If the phone cannot hold the pinned scope, the app asks for a companion instead of evicting pins.

## Phase 3. Provider routing and automatic replacement

**Job:** local fallback. **Repos:** `pubky-app`, the SDK in `pubky/pubky-homeserver`

Build the provider table: roles, scopes, privacy class, order, credentials, cursors, and health per role and scope. Implement the read order: local index, retained slices, live peers, the author's enrolled homeservers, the preferred large indexer, alternate large indexers. Nexus becomes one `index` provider among several. A local hit never contacts it.

Implement the failure classes and cooldowns from the specification. Show local retention, acceptance per homeserver, and indexer visibility as separate fields, and show which role is degraded and who took over.

Add the read side of failover: read every `_pubky` target of a followed identity once the SDK exposes them, take the union of their event streams for new records, fetch home statements from those homeservers and the identity's mirrors, and verify each statement's grant offline. Port the grant, home-statement, and merge vectors.

**Gate:** kill Nexus in the middle of a session. Local answers appear immediately, the next eligible provider takes the `index` role, and no endpoint is edited by hand. A homeserver that refuses one scope stays healthy for another. A private query never reaches a public provider when its private provider fails. A provider's omission never produces a tombstone. The vectors pass, including the unenrolled home, wrong signer, read-only grant, expired grant, stale sequence, delete-after-copy, and disagreeing-homeservers cases.

## Phase 4. Sharing controls and slices

**Job:** P2P indexing. **Repo:** `pubky-app`

Build the sharing controls: share and don't-share choices for keys, all followed keys, shops, single listings or records, tag labels, link domains, and record kinds. A don't-share choice overrides any share choice it overlaps. The controls list public records only. Private favorites, private follows, trust marks, searches, the workspace, transactions, locked bytes, and the last-read marker never appear. The user can see exactly what the current slice contains.

The slice is the result of those choices. The app generates a provider key and gets it a grant through Ring's existing `signin_grant` flow, with write on `/pub/slime.pubky.app/`. The app signs the slice with that key as a detached JWS and publishes it to `pubky://<user>/pub/slime.pubky.app/slices/<n>/`, naming the previous one in `set.json`, whenever the result changes. It publishes a `slices`-only advertisement at `pubky://<user>/pub/slime.pubky.app/providers/<provider-key>.json`. It imports other users' slices into the replica with the provider recorded as supplier.

Add folder export and import. Export a README, optional key and link lists, and `records/<author>/...` holding original bytes, for public record types only. Import by staging, enforcing filename and size rules, previewing, then committing once. Keeping records, following keys, refreshing, and changing sharing choices are separate options at import.

Port the inventory, JWS, slice, and scope checks from the Python checker. Grants and JWS reuse the `pubky-common` helpers.

**Gate:** the slice lists exactly the records the choices select, before and after a choice changes, and a don't-share choice removes what it names. No slice or export contains orders, favorites, private follows, trust marks, searches, or the last-read marker. Reimport is idempotent. Two paths with the same bytes and different origins stay two origins. A tampered signed file fails. A hostile ZIP (path traversal, link, duplicate names) never escapes staging. A second client downloads the first client's slice from its homeserver and builds the same answers to `author`, `label`, and `refs`. A slice whose grant has expired, or cannot write `/pub/slime.pubky.app/`, is rejected. A Rust implementation passes the same vectors as the Python checker.

## Phase 5. Providers, advertisements, and discovery

**Job:** P2P indexing. **Repos:** `pubky-backup` for the companion provider, `pubky-app` for the client, `pubky-nexus` for an optional Slime interface on Nexus

A browser cannot accept connections, so live providers run where a process can listen: a companion built on the `pubky-backup` core, a community host, or a large indexer.

The companion generates a provider key and gets it a grant through Ring's `signin_grant` flow, with write on `/pub/slime.pubky.app/`. It signs `slime-provider/1` with it, serves `provider.json`, `query`, `record`, and the operator's slice, and enforces its advertised limits. Its scopes are the operator's sharing choices. It writes the advertisement to `pubky://<operator>/pub/slime.pubky.app/providers/<provider-key>.json` through its grant session. Exposing the same four primitives on Nexus, under a Synonym provider key, makes Nexus a replaceable provider like the others.

The client builds its configured mesh from user-added providers, shipped defaults, providers run by familiar keys, mirrors and notice providers in familiar keys' services documents, and advertised `peers` within a crawl budget. For each need it asks at most 2 providers whose scope covers it.

**Gate, first part of the headline test:** three clients, with Nexus and every Synonym-operated indexer blocked. Alice follows Dana and Bob. Bob has chosen to share Dana's records, and his companion advertises that choice. Alice's app builds its mesh, finds Bob's provider with no manual endpoint, verifies its grant, imports his slice, tops it up with a live `after` query, and searches Dana's shop and listings with the network blocked. Bob's provider log shows only the keys and URIs Alice's app named, never a search term. The same query against the same provider state returns the same response. A client that follows nobody receives nothing pushed to it.

## Phase 6. Notices

**Job:** P2P indexing, for inbound activity. **Repos:** `pubky-app`, `pubky-backup`

After publishing a record that references another key, the client posts `slime-notice/1` to that key's notice providers and to up to 2 providers whose scopes cover it, meeting each provider's published proof-of-work floor, and retries with backoff for 7 days. A provider accepts a notice when the target key's services document lists it, or when it has the `notices` role and its scopes cover the target key or record. It answers `403` otherwise.

The provider queue follows the Open Inbox design (`hypercolor-web` ADR 0004): reject rather than evict within a target, a cold cap of 4 and a warm cap of 64 per target, a global cap with fair eviction from the deepest target, an optional proof-of-work floor raised under attack, vouched senders (keys the target publicly follows) exempt from the floor, a per-IP token bucket, and every cap published in the advertisement. It fetches and checks each source before indexing it. Unchecked notices are never served.

The recipient drains its notice providers, and providers that cover its key, with `refs` and `after`. It admits each source under the normal rules and derives notifications locally. Sources from keys outside the recipient's trust paths go to a requests view capped at 256 rows, where a stranger can only push out an unviewed row. Rows show the sender's key, arrival time, and provider until the user opens one. Nothing auto-follows or auto-accepts.

**Gate, second part of the headline test:** Carol, whom neither Alice nor Dana follows, tags one of Dana's listings. With Nexus still blocked, Alice sees the tag within one refresh, through Bob's `refs` answer or his next slice. A provider neither listed by the target nor covering it refuses the notice. A notice whose source does not reference its target is never served. A Sybil flood of 10,000 fresh keys against one target leaves the honest notices already queued in place, fills the target's queue, and is then refused with `503`, while notices to other targets still land. The requests view stays at its cap and keeps every viewed row. A stranger's reply to Alice lands in her requests view.

## Phase 7. Publishing failover

**Job:** local fallback, for publishing. **Repos:** Pubky Ring, `pubky/pubky-homeserver` (SDK and homeserver), `pubky-app`, `pubky-backup`

Enrollment runs once through Ring. The user picks one or more alternate homeservers. For each, Ring approves a `signup_grant` for the designated publisher's client key, with write on `/pub/`, so the account exists and the publisher holds a session there. Ring signs one PKARR packet with a `_pubky` record per enrolled homeserver, in priority order. The designated publisher writes the services document.

That packet needs three changes in `pubky/pubky-homeserver`, each small:

1. The SDK publishes several `_pubky` records. Today `build_homeserver_packet` (`pubky-sdk/src/actors/pkdns.rs`) writes one.
2. The SDK tries each `_pubky` target in priority order, as PKARR's endpoint design specifies. Today `extract_host_from_packet` takes the first match.
3. A homeserver republishes a packet that lists it in any `_pubky` record. Today the user-key republisher (`src/republishers/user_keys_republisher.rs`) skips a packet whose first target is another homeserver.

Until they land, publishing still fails over automatically, and other readers follow once Ring moves `_pubky`. The designated publisher and the mirrors in the services document republish the identity's last signed packet unchanged from the start, so a primary that stops republishing cannot make the identity unresolvable.

The designated publisher replicates every authored public record to every enrolled homeserver and tracks acceptance per destination. On persistent refusal, or 3 failures across 10 minutes, it switches to the next healthy enrolled homeserver with a verified copy, writes pending operations there, signs a home statement with the failover key (carrying its grant), and writes it to every reachable enrolled homeserver and the mirrors. It then queues a request for Ring to reorder `_pubky`, and the app says when that has not happened.

Edits and deletes of mutable paths use the 0.13 lock on the path-addressed `/storage` route: `storage.lock`, compare the ETag with the outbox row's base hash, then `put_locked` or a locked delete, then `unlock`. A mismatch leaves the row `conflicted`. Ask the homeserver team for `If-Match` and `If-None-Match: *` on `PUT` and `DELETE` (RFC 9110), which turn this into one request.

**Gate, third part of the headline test:** Synonym's homeserver disables Alice's account for writes (`POST /users/{pubkey}/disable` on its admin API, which refuses writes with 403 and keeps serving reads). Alice's next post publishes on her enrolled alternate with no prompt, and Bob and Carol read it from the union of her enrolled homeservers. Ring was not contacted during the switch, and the app never held the identity seed. With the primary's republisher stopped, Alice still resolves after the DHT would have dropped an unrepublished packet. A home statement naming a homeserver outside Alice's `_pubky` records is ignored. A statement whose signer is not its grant's client key, or whose grant cannot write `/pub/slime.pubky.app/`, is ignored. After the failover key's grant expires, its statements are ignored. Two devices edit one listing while partitioned, and neither a silent last write nor a doubled stock count wins. A returning primary with stale edits does not overwrite an accepted successor. A crash after the local commit and before any acceptance keeps the right state for each destination.

## Phase 8. The headline test

**Job:** both. This is the final gate.

Run the headline test end to end with real clients and independently operated services:

- Alice, Bob, and Carol on separate devices. Bob's provider on a companion host he operates.
- Dana's homeserver, Carol's homeserver, and Alice's enrolled alternate each run by an operator other than Synonym. Alice's primary is Synonym's homeserver.
- Nexus removed completely: its hostnames resolve nowhere for the whole run. PKARR resolves through a non-Synonym relay or the DHT directly.
- Dana publishes one new record after Nexus is gone, so the test cannot pass on a static cache.

**Pass when**, with no manual endpoint edits and no Synonym service answering any request:

1. Alice follows Dana. Her app finds Bob's provider through her configured mesh, pulls Dana's shop records, listings (including the new one), tags, and images, and searches them with the network blocked.
2. Carol tags one of Dana's listings. Alice sees the tag through Bob's index or a notice.
3. Synonym's homeserver refuses Alice's writes. Alice publishes a post. Her enrolled alternate accepts it, her home statement names that alternate, and Bob and Carol read the post.
4. Alice's identity seed stays in Ring throughout, and none of Alice's searches, favorites, private follows, trust marks, or unshared records appear in any request, slice, or advertisement.

Repeat the run with the failures in a different order, and once with all of them at the same time. Independence means separate operators and machines, not two hostnames on one backend.

## What each phase is allowed to claim

| After | Claim |
|---|---|
| 0 | Offline reading and composing for data already on the device. |
| 1 | The app answers from its own index, built from original records of any type. |
| 2 | Followed keys, shops, and listings stay current without Nexus and browse offline with their dependencies. |
| 3 | Every read role is replaceable automatically. Nexus is one provider among several. |
| 4 | Users choose what they share, and publish exactly that as a slice anyone can search privately. |
| 5 | Peers discover each other's providers and fill each other's indexes without a central indexer. |
| 6 | Replies, tags, follows, and mentions from unknown keys arrive without a central indexer. |
| 7 | Publishing fails over automatically within the enrolled set, without the identity seed leaving Ring. |
| 8 | The headline test passes. Nexus and the Synonym homeserver are conveniences. |

## Not in this plan

| Work | Reason |
|---|---|
| New PKARR records, or a global index of tags or keys in the DHT | Slices and providers carry the index. The identity's PKARR packet keeps only `_pubky`. |
| A new key delegation mechanism | Slime keys are the client keys of Pubky grants. |
| A custom conditional-write endpoint | The homeserver's WebDAV lock covers it; `If-Match` is the standard remainder. |
| Author signatures on records | No Pubky client can produce them. A record's authority is its author's homeserver and event stream. |
| Shared rankings, consensus on index contents, universal reputation | Providers return candidates. Each reader ranks locally. |
| Flooding gossip or broadcast search | References are followed one hop at a time. Queries name only what the user asked. |
| A torrent client in the app | Folders, ZIP, HTTP, and homeservers carry slices. A torrent MAY carry a snapshot. |
| A homeserver process in the browser | The replica is in-process storage. Live providers run on companions and hosts. |
| The app changing the identity's PKARR packet | Ring owns the identity seed. The failover key names the active home within the enrolled set. |
| A message protocol | Notices are pointers to public records. |
| A shop, listing, or review schema | Slime retains, shares, and indexes whatever records sellers publish. |
| Running an imported recipe | A preference is data. |

## Tests

Each phase lists the behavior that closes it. An import mock does not close offline boot. The Python checker does not close Ring issuance, companion serving, or homeserver acceptance. Those need real clients and real services.

The checker suite covers what files can show: folders, detached JWS signatures, hostile archives, real pubky.app records and their ids, dependency chains and states, slices and their scopes, provider selection, query responses, notices with their acceptance and flood rules, Pubky grants, services documents, home statements, merges over homeserver event streams, and the headline test's data path offline (`examples/test_headline.py`). Every phase that ports a format ports its vectors, and the App's copy runs in CI.
