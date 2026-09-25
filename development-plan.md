# Slime development plan

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **P2P indexing.** Peers share what they already know: records, tags, follows, shops, listings, and whatever parts of their own index they choose to share. The network stays densely indexed without any single indexer, and anyone can discover it and crawl it.
2. **Local fallback.** When an indexer or a homeserver is disrupted or censored, the app keeps working from local state and replaceable providers. Reading, search, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable.

This plan builds both jobs into Pubky App and ends on one test:

> Alice, Bob, and Carol use Pubky App. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely. Alice follows Dana. Bob already retains Dana's shop, listings, and tags, has chosen to share them, and his Slime provider advertises that choice. Alice's app finds Bob's provider through her configured mesh, pulls Dana's shop, listings, and tags, builds them into her local index, and searches them offline. Carol publishes a new tag on one of Dana's listings. Alice sees it through Bob's index or a notice, with no Synonym service involved. Then Synonym's homeserver starts refusing Alice's writes. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, her public location moves to that alternate, and Bob and Carol read the post. Alice's identity seed never leaves Pubky Ring.

Each phase closes one piece of that test. The rules are in the [specification](spec.md). The data each phase must cover is the [coverage matrix](spec.md#1-coverage).

Use the existing SDK, homeserver event streams, PKARR, the record types in `pubky-app-specs`, Unified Key Delegation (UKD) for subordinate keys, Paykit, Locks, and `pubky-backup`. Do not open a new protocol repository until a second implementation needs a shared crate. Read the current `pubky/pubky-app` sources for posts, session restore, and homeserver signup before editing.

Reference fixtures and a Python checker live in [examples/](examples/README.md). They cover folders, signatures, shared indexes, advertisements, query responses, notices, routes, home statements, and the headline test's data path. Port those vectors. They do not show that the App survives a restart, that Ring issues a delegation, or that a homeserver accepts a write. Those gates need real clients.

## Phase 0. Durable workspace

**Job:** local fallback. **Repo:** `pubky/pubky-app`

Split local storage into workspace, record store, and derived index. A schema rebuild may drop the derived index only. Drafts, outbox rows, favorites, trust marks, sharing choices, and private settings survive.

An outbox row has a local operation id, account, target URI, intended bytes, dependency ids, known base version, and a state per destination: `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, or `conflicted`. Persist the row and the bytes before the interface reports local success. If the homeserver throws, keep the row. Do not delete the local post.

Ship a private workspace export in this phase. It is a file the user saves, not a public set.

**Gate:** cold start of the installed app with no network and with session refresh failing. Retained data reads. Kill the process after queueing a post and find it after restart. Expire the session while offline and keep the work. Rebuild the derived index and lose nothing in the workspace.

**Stop if:** the fix needs the identity seed in the page. That belongs in Ring.

## Phase 1. The replica and its local index

**Job:** both. **Repos:** `pubky-app`, `pubky-app-specs`

Store original bytes by origin URI and SHA-256. Implement the replica interface: `get`, `list`, `putLocal`, `deleteLocal`, `events`, `versions`, `dependencies`, and `query`. The app renders from it.

Write one adapter per `pubky-app-specs` record type (profile, post, follow, mute, tag, bookmark, feed, file, blob) that turns a record into an entry. Every other record, including whatever a seller publishes for a shop or listing, becomes kind `other`, with refs taken from the `pubky://` and http URIs in its body. Slime does not wait on, or depend on, any shop or listing schema.

Implement the four primitives (`author`, `label`, `refs`, `domain`, each with `after`) over retained entries. The following feed lists retained authors' posts. It is not a saved list of indexer ids. An indexer response enters the record store only after the original fields are taken out. Anything the indexer added stays labeled as its claim.

**Gate:** rebuild the index with the network blocked and recover the following feed, tags, known replies, followers already seen, and every retained record of followed sellers. The ported `LocalIndex` vectors return the same answers, including refs extracted from records of unknown type. An entry that disagrees with its bytes is rejected. A newer body is never attached to an older event hash.

## Phase 2. Familiar scope, followed shops, and dependencies

**Job:** both. **Repos:** `pubky-app`, the SDK in `pubky-core`, `paykit-rs`, `pubky-locks`

Collect the familiar scope from homeservers during ordinary use: follows, trust marks, and the sellers behind followed shops and listings. Resolve each key's homeserver with the SDK, read scoped events, group keys by host, and keep one cursor per provider and scope. Persist the event before advancing the cursor. Reconcile after a suspected reset.

Following a shop is a follow of the seller's key. Following a listing is a public bookmark. A private follow or favorite is a workspace pin. All of them retain every public record of the seller, the seller profile, the tags and other records that reference them, and their media within budget.

Track dependencies per record as `retained`, `missing`, `fetchable`, or `withheld`. Fetch text dependencies with the record. Media follows its own budget. Start with 4 requests in flight, 2 per host, a 128 MiB text target, and no automatic graph expansion, then measure.

Buy hands the seller and the record reference to Paykit, which checks the live counterparty. A Lock applies only when the record is access-gated. A retained copy does not reserve stock or override a newer version from the seller.

**Gate:** with every large indexer blocked, familiar keys refresh from their homeservers. A followed shop, public or private, browses and searches offline with its images. A listing whose image was never fetched shows the gap, not a removal. A packet capture while browsing retained shops offline shows no sockets, no analytics, no remote images, and no quote request. No outgoing request names a privately followed shop. A known record missing from an index response is not shown as deleted.

Time fixtures of 50, 250, and 2,500 familiar keys on a phone. If the phone cannot hold the pinned scope, the app asks for a companion instead of evicting pins.

## Phase 3. Provider routing and automatic replacement

**Job:** local fallback. **Repos:** `pubky-app`, the SDK in `pubky-core`

Build the provider table: roles, scopes, privacy class, order, credentials, cursors, and health per role and scope. Implement the read order: local index, retained shared indexes, live peers, the author's homeservers, the preferred large indexer, alternate large indexers. Nexus becomes one `index` provider among several. A local hit never contacts it.

Implement the failure classes and cooldowns from the specification. Show local retention, acceptance per homeserver, and indexer visibility as separate fields, and show which role is degraded and who took over.

Add the read side of routes and home statements: fetch a followed identity's route and home statements from its enrolled homeservers and mirrors, verify the route against the identity key, and verify each home statement against the route and the UKD delegation of its failover key. The SDK's UKD verifier supplies the delegation check. Port the `verify_route`, `verify_home`, and `resolve_home` vectors.

**Gate:** kill Nexus in the middle of a session. Local answers appear immediately, the next eligible provider takes the `index` role, and no endpoint is edited by hand. A homeserver that refuses one scope stays healthy for another. A private query never reaches a public provider when its private provider fails. A provider's omission never produces a tombstone. The home-statement vectors pass, including the unenrolled home, wrong signer, revoked delegation, expired delegation, and stale sequence cases.

## Phase 4. Sharing controls and shared indexes

**Job:** P2P indexing. **Repos:** `pubky-app`, Pubky Ring

Build the sharing controls: share and don't-share choices for keys, all followed keys, shops, single listings or records, tag labels, link domains, and record kinds. A don't-share choice overrides any share choice it overlaps. The controls list public records only. Private favorites, private follows, trust marks, searches, the workspace, transactions, and locked bytes never appear. The user can see exactly what the current shared index contains.

The shared index is the result of those choices. Ring delegates a provider key to the app through UKD: an AppCert, and an entry in the identity's `slime` KeyBinding. The app signs the shared index with that key and publishes it to `pubky://<user>/pub/slime/indexes/<n>/`, naming the previous one in `set.json`, whenever the result changes. It publishes an `indexes`-only advertisement at `pubky://<user>/pub/slime/providers/<provider-key>.json`. It imports other users' shared indexes into the replica with the provider recorded as supplier.

Add folder export and import. Export a README, optional key and link lists, and `records/<author>/...` holding original bytes, for public record types only. Import by staging, enforcing filename and size rules, previewing, then committing once. Keeping records, following keys, refreshing, and changing sharing choices are separate options at import.

Port the inventory, signature, shared-index, and scope checks from the Python checker. Signing a set with the identity key itself waits for a Ring typed transcript for `slime/set/1`. Provider-key signing does not.

**Gate:** the shared index lists exactly the records the choices select, before and after a choice changes, and a don't-share choice removes what it names. No shared index or export contains orders, favorites, private follows, trust marks, or searches. Reimport is idempotent. Two paths with the same bytes and different origins stay two origins. A tampered signed file fails. A hostile ZIP (path traversal, link, duplicate names) never escapes staging. A second client downloads the first client's shared index from its homeserver and builds the same answers to `author`, `label`, and `refs`. Revoking the provider key through a new KeyBinding makes other clients reject its next shared index. A second implementation, starting with the Python checker and then a Rust vector, accepts an unchanged shared index after recompression and rejects any change.

## Phase 5. Providers, advertisements, and discovery

**Job:** P2P indexing. **Repos:** `pubky-backup` for the companion provider, `pubky-app` for the client, `pubky-nexus` for an optional Slime interface on Nexus

A browser cannot accept connections, so live providers run where a process can listen: a companion built on the `pubky-backup` core, a community host, or a large indexer. Pin the backup core to a release before starting.

Ring delegates a provider key to the companion through UKD. The companion signs `slime-provider/1` with it, serves `provider.json`, `query`, `record`, and the operator's shared index, and enforces its advertised limits. Its scopes are the operator's sharing choices. The operator's app copies the advertisement to `pubky://<operator>/pub/slime/providers/<provider-key>.json`. Exposing the same four primitives on Nexus, under a Synonym provider key, makes Nexus a replaceable provider like the others.

The client builds its configured mesh from user-added providers, shipped defaults, providers run by familiar keys, mirrors and notice providers in familiar keys' routes, and advertised `peers` within a crawl budget. For each need it asks at most 2 providers whose scope covers it.

**Gate, first part of the headline test:** three clients, with Nexus and every Synonym-operated indexer blocked. Alice follows Dana and Bob. Bob has chosen to share Dana's records, and his companion advertises that choice. Alice's app finds Bob's provider with no manual endpoint, verifies its delegation, imports his shared index, tops it up with a live `after` query, and searches Dana's shop and listings with the network blocked. Bob's provider log shows only the keys and URIs Alice's app named, never a search term. The same query against the same provider state returns the same response. A client that follows nobody receives nothing pushed to it.

## Phase 6. Notices

**Job:** P2P indexing, for inbound activity. **Repos:** `pubky-app`, `pubky-backup`

After publishing a record that references another key, the client posts `slime-notice/1` to that key's notice providers and to up to 2 providers whose scopes cover it, retrying with backoff for 7 days. A provider accepts a notice when the target key's route lists it, or when it has the `notices` role and its scopes cover the target key or record. It answers `403` otherwise. It rate-limits per source author and per target, fetches and checks each source, and indexes it so it answers `refs`. Unchecked notices are never served.

The recipient drains its notice providers, and providers that cover its key, with `refs` and `after`. It admits each source under the normal rules and derives notifications locally. Sources from keys outside the recipient's trust paths go to a requests view. Nothing auto-follows or auto-accepts.

**Gate, second part of the headline test:** Carol, whom neither Alice nor Dana follows, tags one of Dana's listings. With Nexus still blocked, Alice sees the tag within one refresh, through Bob's `refs` answer or his next shared index. A provider neither listed by the target nor covering it refuses the notice. A notice whose source does not reference its target is never served. A flood of notices from one key is rate-limited without delaying notices from others. A stranger's reply to Alice lands in her requests view.

## Phase 7. Publishing failover

**Job:** local fallback, for publishing. **Repos:** Pubky Ring, the SDK in `pubky-core`, the homeserver, `pubky-app`, `pubky-backup`

Enrollment runs once through Ring. The user picks one or more alternate homeservers. Ring signs the user up on each and authorizes the designated publisher with a session on each. The designated publisher generates the failover key. Ring issues its AppCert, lists it in the identity's `slime` KeyBinding, and signs the route through a typed `slime-route` transcript. The route is written to every enrolled homeserver. Ring gains two capabilities here: UKD issuance for `slime` AppKeys, and the `slime-route` transcript. It gains no general signing call.

The designated publisher replicates every authored public record to every enrolled homeserver and tracks acceptance per destination. On persistent refusal, or 3 failures across 10 minutes, it switches to the next healthy enrolled homeserver with a verified copy, writes pending operations there, signs a home statement with the failover key, and writes it to every reachable enrolled homeserver and the route's mirrors. It then queues a request for Ring to move `_pubky`, and the app says when that has not happened.

New records publish automatically after a switch. Edits and deletes of mutable paths stay `conflicted` until the homeserver ships `apply(operation_id, origin, expected_version_or_absent, action, body)`. A client GET followed by PUT does not qualify.

**Gate, third part of the headline test:** Synonym's homeserver refuses Alice's writes. Alice's next post publishes on her enrolled alternate with no prompt, and Bob and Carol read it by following her home statement. Ring was not contacted during the switch, and the app never held the identity seed. A home statement naming a homeserver outside the route is ignored. A statement signed by any key other than the route's failover key is ignored. After Ring publishes a KeyBinding without the failover key, its statements are ignored. An edit to a mutable listing during the switch stays `conflicted`. After `apply` ships: two devices edit one listing while partitioned, and neither a silent last write nor a doubled stock count wins; a returning primary with stale edits does not overwrite an accepted successor; a crash after the local commit and before any acceptance keeps the right state for each destination.

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
4. Alice's identity seed stays in Ring throughout, and none of Alice's searches, favorites, private follows, trust marks, or unshared records appear in any request, shared index, or advertisement.

Repeat the run with the failures in a different order, and once with all of them at the same time. Independence means separate operators and machines, not two hostnames on one backend.

## What each phase is allowed to claim

| After | Claim |
|---|---|
| 0 | Offline reading and composing for data already on the device. |
| 1 | The app answers from its own index, built from original records of any type. |
| 2 | Followed keys, shops, and listings stay current without Nexus and browse offline with their dependencies. |
| 3 | Every read role is replaceable automatically. Nexus is one provider among several. |
| 4 | Users choose what they share, and publish exactly that as a shared index anyone can search privately. |
| 5 | Peers discover each other's providers and fill each other's indexes without a central indexer. |
| 6 | Replies, tags, follows, and mentions from unknown keys arrive without a central indexer. |
| 7 | Publishing fails over automatically within the enrolled set, without the identity seed leaving Ring. |
| 8 | The headline test passes. Nexus and the Synonym homeserver are conveniences. |

## Not in this plan

| Work | Reason |
|---|---|
| New PKARR records, or a global index of tags or keys in the DHT | Shared indexes and providers carry the index. The identity's PKARR packet keeps only `_pubky`. |
| A new key delegation mechanism | Slime keys are UKD AppKeys. |
| Shared rankings, consensus on index contents, universal reputation | Providers return candidates. Each reader ranks locally. |
| Flooding gossip or broadcast search | References are followed one hop at a time. Queries name only what the user asked. |
| A torrent client in the app | Folders, ZIP, HTTP, and homeservers carry shared indexes. A torrent MAY carry a snapshot. |
| A homeserver process in the browser | The replica is in-process storage. Live providers run on companions and hosts. |
| The app changing the identity's PKARR packet | Ring owns the identity seed. The failover key names the active home within the enrolled set. |
| A message protocol | Notices are pointers to public records. |
| A shop, listing, or review schema | Slime retains, shares, and indexes whatever records sellers publish. |
| Running an imported recipe | A preference is data. |

## Tests

Each phase lists the behavior that closes it. An import mock does not close offline boot. The Python checker does not close Ring issuance, companion serving, or homeserver acceptance. Those need real clients and real services.

The checker suite covers what files can show: folders, signatures, merge, shared indexes and their scopes, advertisements, query responses, notices and the acceptance rule, routes, home statements, and the headline test's data path offline (`examples/test_headline.py`). UKD verification belongs to the UKD library. The checker takes its verified output as input. Every phase that ports a format ports its vectors, and the App's copy runs in CI.
