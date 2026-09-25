# Slime development plan

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **P2P indexing.** Peers share what they already know: records, tags, follows, shops, listings, and slices of their own index. The network stays densely indexed without any single indexer, and anyone can discover it and crawl it.
2. **Local fallback.** When an indexer or a homeserver is disrupted or censored, the app keeps working from local state and replaceable providers. Reading, search, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable.

This plan builds both jobs into Pubky App and ends on one test:

> Alice, Bob, and Carol use Pubky App. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely. Alice follows Dana. Bob already retains Dana's shop, listings, and tags, and his Slime provider advertises that scope. Alice's app finds Bob's provider through her configured mesh, pulls Dana's shop, listings, and tags, builds them into her local index, and searches them offline. Carol publishes a new tag on one of Dana's listings. Alice sees it through Bob's index or a notice, with no Synonym service involved. Then Synonym's homeserver starts refusing Alice's writes. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, her public location moves to that alternate, and Bob and Carol read the post. Alice's identity seed never leaves Pubky Ring.

Each phase closes one piece of that test. The rules are in the [specification](spec.md). The data each phase must cover is the [coverage matrix](spec.md#1-coverage).

Use the existing SDK, homeserver event streams, PKARR, tags, Paykit, Locks, and `pubky-backup`. Do not open a new protocol repository until a second implementation needs a shared crate. Read the current `pubky/pubky-app` sources for posts, session restore, and homeserver signup before editing.

Reference fixtures and a Python checker live in [examples/](examples/README.md). They cover folders, signatures, slices, advertisements, query responses, notices, routes, and the headline test's data path. Port those vectors. They do not show that the App survives a restart or that a homeserver accepts a write. Those gates need real clients.

## Phase 0. Durable workspace

**Job:** local fallback. **Repo:** `pubky/pubky-app`

Split local storage into workspace, record store, and derived index. A schema rebuild may drop the derived index only. Drafts, outbox rows, favorites, trust marks, and private settings survive.

An outbox row has a local operation id, account, target URI, intended bytes, dependency ids, known base version, and a state per destination: `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, or `conflicted`. Persist the row and the bytes before the interface reports local success. If the homeserver throws, keep the row. Do not delete the local post.

Ship a private workspace export in this phase. It is a file the user saves, not a public set.

**Gate:** cold start of the installed app with no network and with session refresh failing. Retained data reads. Kill the process after queueing a post and find it after restart. Expire the session while offline and keep the work. Rebuild the derived index and lose nothing in the workspace.

**Stop if:** the fix needs the identity seed in the page. That belongs in Ring.

## Phase 1. The replica and its local index

**Job:** both. **Repos:** `pubky-app`, record schemas in `pubky-app-specs`

Store original bytes by origin URI and SHA-256. Implement the replica interface: `get`, `list`, `putLocal`, `deleteLocal`, `events`, `versions`, `dependencies`, and `query`. The app renders from it.

Write adapters that turn records into entries: profiles, posts and replies, follows, mutes, tags, bookmarks, and custom feeds from the Pubky App schema. Add shop, listing, and review adapters for the deployed commerce schema. The marketplace objects under `/pub/pubky.app/marketplace/v1/` in the `pubky-app-specs` marketplace branch are the current candidate. Name the owner and the release before rendering prices or stock. Until then, shop records stay opaque.

Implement the four primitives (`author`, `label`, `refs`, `domain`, each with `after`) over retained entries. The following feed lists retained authors' posts. It is not a saved list of indexer ids. An indexer response enters the record store only after the original fields are taken out. Anything the indexer added stays labeled as its claim.

**Gate:** rebuild the index with the network blocked and recover the following feed, tags, known replies, followers already seen, and the catalog of retained shops. The ported `LocalIndex` vectors return the same answers. An entry that disagrees with its bytes is rejected. A newer body is never attached to an older event hash.

## Phase 2. Familiar scope, followed shops, and dependencies

**Job:** both. **Repos:** `pubky-app`, the SDK in `pubky-core`, `paykit-rs`, `pubky-locks`

Collect the familiar scope from homeservers during ordinary use: follows, trust marks, and the sellers of followed shops and listings. Resolve each key's homeserver with the SDK, read scoped events, group keys by host, and keep one cursor per provider and scope. Persist the event before advancing the cursor. Reconcile after a suspected reset.

Followed shops and followed listings get both forms. A public follow or public bookmark makes the seller familiar. A private follow or favorite pins the shop record, every listing, the seller profile, the tags and reviews on them, and their media within budget, and shares none of it.

Track dependencies per record as `retained`, `missing`, `fetchable`, or `withheld`. Fetch text dependencies with the record. Media follows its own budget. Start with 4 requests in flight, 2 per host, a 128 MiB text target, and no automatic graph expansion, then measure.

Buy hands the seller and the listing reference to Paykit, which checks the live counterparty. A Lock applies only when the record is access-gated. A retained catalog does not reserve stock or revive a withdrawn listing.

**Gate:** with every large indexer blocked, familiar keys refresh from their homeservers. A followed shop, in both forms, browses and searches offline with its images. A listing whose image was never fetched shows the gap, not a removal. A packet capture while browsing the retained catalog offline shows no sockets, no analytics, no remote images, and no quote request. No outgoing request names a privately followed shop. A known record missing from an index response is not shown as deleted.

Time fixtures of 50, 250, and 2,500 familiar keys on a phone. If the phone cannot hold the pinned scope, the app asks for a companion instead of evicting pins.

## Phase 3. Provider routing and automatic replacement

**Job:** local fallback. **Repos:** `pubky-app`, the SDK in `pubky-core`

Build the provider table: roles, scopes, privacy class, order, credentials, cursors, and health per role and scope. Implement the read order: local index, retained slices, live peers, the author's homeservers, the preferred large indexer, alternate large indexers. Nexus becomes one `index` provider among several. A local hit never contacts it.

Implement the failure classes and cooldowns from the specification. Show local retention, acceptance per homeserver, and indexer visibility as separate fields, and show which role is degraded and who took over.

Add route-aware resolution on the read side. The SDK exposes a key's `_slime` TXT record. The client checks a route against its pin and accepts a failover record under the rules in the specification. Port the `resolve_home` vectors.

**Gate:** kill Nexus in the middle of a session. Local answers appear immediately, the next eligible provider takes the `index` role, and no endpoint is edited by hand. A homeserver that refuses one scope stays healthy for another. A private query never reaches a public provider when its private provider fails. A provider's omission never produces a tombstone. The failover-record vectors pass, including the stale, expired, unenrolled, and wrong-key cases.

## Phase 4. Folders and index slices

**Job:** P2P indexing. **Repos:** `pubky-app`, Pubky Ring

Export a README, optional key and link lists, and `records/<author>/...` holding original bytes. Allow public record types only. Deny drafts, read state, searches, carts, orders, addresses, payment requests, tokens, trust marks, private favorites, private follows, and unlocked Lock content. Import by staging, enforcing filename and size rules, previewing, then committing once. Offer separate choices to keep records, follow keys, refresh, and share. Only "keep records" defaults on.

Add slices. The app generates a provider key for this account, keeps it in the workspace, and signs slices with it. It publishes a thin slice of its public familiar scope to `pubky://<user>/pub/slime/slices/<n>/` at least daily and when that scope changes, and names the previous slice in `set.json`. It publishes a `slices`-only advertisement for that key at `pubky://<user>/pub/slime/provider.json`, so anyone who follows the user can find the slice. It imports slices from other providers into the replica with the provider recorded as supplier.

Port the inventory, signature, and slice checks from the Python checker. Signing a set with an identity key waits for a Ring signing call with the `slime/set/1` domain. Provider-key signing does not.

**Gate:** reimport is idempotent. Two paths with the same bytes and different origins stay two origins. A public export and a slice contain no private orders, favorites, private follows, trust marks, or searches. A tampered signed file fails. A hostile ZIP (path traversal, link, duplicate names) never escapes staging. A second client downloads the first client's slice from its homeserver and builds the same answers to `author`, `label`, and `refs`. A second implementation, starting with the Python checker and then a Rust vector, accepts an unchanged slice after recompression and rejects any change.

## Phase 5. Providers, advertisements, and discovery

**Job:** P2P indexing. **Repos:** `pubky-backup` for the companion provider, `pubky-app` for the client, `pubky-nexus` for an optional Slime interface on Nexus

A browser cannot accept connections, so live providers run where a process can listen: a companion built on the `pubky-backup` core, a community host, or a large indexer. Pin the backup core to a release before starting.

The companion signs `slime-provider/1` with its provider key, serves `provider.json`, `query`, `record`, and its slices, and enforces its advertised limits. It publishes its own PKARR `_slime` record with `ad=` and `ep=`, and the operator's app copies the advertisement to `pubky://<operator>/pub/slime/provider.json`. Its default scope is the operator's public follows and public bookmarks. It never takes scope from trust marks or private favorites. Exposing the same four primitives on Nexus makes Nexus a replaceable provider like the others.

The client builds its configured mesh from user-added providers, shipped defaults, providers run by familiar keys, mirrors and notice providers in familiar keys' routes, and advertised `peers` within a crawl budget. For each need it asks at most 2 providers whose scope covers it.

**Gate, first part of the headline test:** three clients, with Nexus and every Synonym-operated indexer blocked. Alice follows Dana and Bob. Bob's companion retains Dana's scope and advertises it. Alice's app finds Bob's provider with no manual endpoint, imports his slice, tops it up with a live `after` query, and searches Dana's shop and listings with the network blocked. Bob's provider log shows only the keys and URIs Alice's app named, never a search term. The same query against the same provider state returns the same response. A client that follows nobody receives nothing pushed to it.

## Phase 6. Notices

**Job:** P2P indexing, for inbound activity. **Repos:** `pubky-app`, `pubky-backup`

After publishing a record that references another key, the client posts `slime-notice/1` to that key's notice providers and to up to 2 providers that advertise its key scope, retrying with backoff for 7 days. Providers accept notices for keys they serve, rate-limit per source author and per target, fetch and check each source, and index it so it answers `refs`. Unchecked notices are never served.

The recipient drains its notice providers with `refs` and `after`, admits each source under the normal rules, and derives notifications locally. Sources from keys outside the recipient's trust paths go to a requests view. Nothing auto-follows or auto-accepts. Users list notice providers in their route (Phase 7). Until then, the client uses providers that advertise the user's key scope.

**Gate, second part of the headline test:** Carol, whom neither Alice nor Dana follows, tags one of Dana's listings. With Nexus still blocked, Alice sees the tag within one refresh, through Bob's `refs` answer or his next slice. A notice whose source does not reference its target is never served. A flood of notices from one key is rate-limited without delaying notices from others. A stranger's reply to Alice lands in her requests view.

## Phase 7. Publishing failover

**Job:** local fallback, for publishing. **Repos:** Pubky Ring, the SDK in `pubky-core`, the homeserver, `pubky-app`, `pubky-backup`

Enrollment runs once through Ring. The user picks at least one alternate homeserver, preferably from another operator. Ring signs the user up there and authorizes the designated publisher with a session on each. The designated publisher generates the failover key and gives Ring its public key. Ring adds `_slime rt=<route hash>` to the identity's PKARR packet and keeps `_pubky`. The route is written to every enrolled homeserver. The SDK and Ring preserve `_slime` whenever they republish.

The designated publisher replicates every authored public record to every enrolled homeserver and tracks acceptance per destination. On persistent refusal, or 3 failures across 10 minutes, it switches to the next healthy enrolled homeserver with a verified copy, writes pending operations there, and publishes the failover key's `_slime` record with a higher `seq`. It then queues a request for Ring to move `_pubky`, and the app says when that has not happened.

New records publish automatically after a switch. Edits and deletes of mutable paths stay `conflicted` until the homeserver ships `apply(operation_id, origin, expected_version_or_absent, action, body)`. A client GET followed by PUT does not qualify.

**Gate, third part of the headline test:** Synonym's homeserver refuses Alice's writes. Alice's next post publishes on her enrolled alternate with no prompt, and Bob and Carol read it through her failover record. Ring was not contacted during the switch, and the app never held the identity seed. An SDK republish of Alice's identity packet keeps `_slime`. A failover record naming a homeserver outside the route is ignored. An edit to a mutable listing during the switch stays `conflicted`. After `apply` ships: two devices edit one listing while partitioned, and neither a silent last write nor a doubled stock count wins; a returning primary with stale edits does not overwrite an accepted successor; a crash after the local commit and before any acceptance keeps the right state for each destination.

## Phase 8. The headline test

**Job:** both. This is the final gate.

Run the headline test end to end with real clients and independently operated services:

- Alice, Bob, and Carol on separate devices. Bob's provider on a companion host he operates.
- Dana's homeserver, Carol's homeserver, and Alice's enrolled alternate each run by an operator other than Synonym. Alice's primary is Synonym's homeserver.
- Nexus removed completely: its hostnames resolve nowhere for the whole run. PKARR resolves through a non-Synonym relay or the DHT directly.
- Dana publishes one new listing after Nexus is gone, so the test cannot pass on a static cache.

**Pass when**, with no manual endpoint edits and no Synonym service answering any request:

1. Alice follows Dana. Her app finds Bob's provider through her configured mesh, pulls Dana's shop, listings (including the new one), tags, and images, and searches them with the network blocked.
2. Carol tags one of Dana's listings. Alice sees the tag through Bob's index or a notice.
3. Synonym's homeserver refuses Alice's writes. Alice publishes a post. Her enrolled alternate accepts it, her failover record names that alternate, and Bob and Carol read the post.
4. Alice's identity seed stays in Ring throughout, and none of Alice's searches, favorites, private follows, or trust marks appear in any request, slice, or advertisement.

Repeat the run with the failures in a different order, and once with all of them at the same time. Independence means separate operators and machines, not two hostnames on one backend.

## What each phase is allowed to claim

| After | Claim |
|---|---|
| 0 | Offline reading and composing for data already on the device. |
| 1 | The app answers from its own index, built from original records. |
| 2 | Followed keys, shops, and listings stay current without Nexus and browse offline with their dependencies. |
| 3 | Every read role is replaceable automatically. Nexus is one provider among several. |
| 4 | People exchange folders and index slices of attributed records. Every user's homeserver hosts a passive slice. |
| 5 | Peers discover each other's providers and fill each other's indexes without a central indexer. |
| 6 | Replies, tags, follows, and mentions from unknown keys arrive without a central indexer. |
| 7 | Publishing fails over automatically within the enrolled set, without the identity seed leaving Ring. |
| 8 | The headline test passes. Nexus and the Synonym homeserver are conveniences. |

## Not in this plan

| Work | Reason |
|---|---|
| A global index of tags or keys in the DHT | PKARR carries per-key pointers only. Slices and providers carry the index. |
| Shared rankings, consensus on index contents, universal reputation | Providers return candidates. Each reader ranks locally. |
| Flooding gossip or broadcast search | References are followed one hop at a time. Queries name only what the user asked. |
| A torrent client in the app | Folders, ZIP, HTTP, and homeservers carry slices. A torrent MAY carry a snapshot. |
| A homeserver process in the browser | The replica is in-process storage. Live providers run on companions and hosts. |
| The app changing the identity's PKARR packet | Ring owns the identity seed. The failover key moves the active home within the enrolled set. |
| A message protocol | Notices are pointers to public records. |
| A listing schema owned by Slime | Adapters follow the records that already exist. |
| Running an imported recipe | A preference is data. |

## Tests

Each phase lists the behavior that closes it. An import mock does not close offline boot. The Python checker does not close Ring enrollment, companion serving, or homeserver acceptance. Those need real clients and real services.

The checker suite covers what files can show: folders, signatures, merge, slices, advertisements, query responses, notices, routes, and the headline test's data path offline (`examples/test_headline.py`). Every phase that ports a format ports its vectors, and the App's copy runs in CI.
