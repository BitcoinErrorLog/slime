# Slime development plan

Slime (Social Latent Intelligence Mesh Exchange) has two jobs.

1. **Replaceable, verifiable indexing.** Several independent indexers provide discovery and search, and any of them can be replaced. Every record carries its author's signature, so every copy and every indexer answer can be checked. Anyone can also publish a signed slice of what they keep, the smallest indexer there is. Indexers do search. Slices do not.
2. **Local fallback.** When an indexer or a homeserver is disrupted or refuses service, the app keeps working from local state and replaceable providers. Reading, search over what is retained, browsing followed shops and listings, composing, and publishing all continue. The switch is automatic.

Synonym and every other provider is automatically replaceable.

This plan builds both jobs into Pubky App and ends on one test and its harder variants:

> Alice, Bob, and Carol use Pubky App on Synonym's homeserver. Dana sells prints from her own homeserver. Synonym's Nexus disappears completely, and Alice's app fails over to a second indexer that Synonym does not run. Then Dana's homeserver goes dark. Alice still opens Dana's shop, listings, and tags, because Bob's slice and the indexer both hold them and every copy carries Dana's signature, and she searches them offline. A forged copy of one listing, with a different price, is rejected rather than shown. Carol tags a listing, and Alice finds the tag through the indexer. Then Synonym's homeserver stops accepting Alice's writes while still serving stale reads. Alice publishes a new post. An alternate homeserver she enrolled earlier accepts it, readers find it through the homeservers her PKARR record lists, and her edits follow her signed home statement. Alice's identity seed never leaves Pubky Ring.

Each phase closes one piece of that test. The rules are in the [specification](spec.md). The data each phase must cover is the [coverage matrix](spec.md#1-coverage).

Build on the current releases: the Pubky SDK 0.13 (crate `pubky`, npm `@synonymdev/pubky`) from `pubky/pubky-homeserver`, which adds grants, path-addressed `/storage`, and WebDAV locks; `pubky-app-specs` 0.8.1 for record types; homeserver event streams; PKARR; Pubky grants for every signing key; Paykit; `pubky/locks`; and `pubky-backup`. Read the current `pubky/pubky-app` sources for posts, session restore, and homeserver signup before editing.

The base comes first, in order: the local replica (phases 0 to 2), several homeservers in the PKARR record (phase 3), author signatures at write time (phase 4), and replaceable indexers (phase 5). Signed indexer answers and static slices come on top (phase 6). Publishing failover and the headline variants close it (phases 7 and 8).

Reference fixtures and a Python checker live in [examples/](examples/README.md). They use real pubky.app records with author signatures. Port those vectors. They do not show that the App survives a restart, that an indexer fails over, that Ring signs a grant, or that a homeserver accepts a write. Those gates need real clients.

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

## Phase 3. Several homeservers in the PKARR record

**Job:** local fallback. **Repos:** `pubky/pubky-homeserver` (SDK and homeserver), Pubky Ring, `pubky-app`

Three small changes in `pubky/pubky-homeserver`:

1. The SDK publishes several `_pubky` records. Today `build_homeserver_packet` (`pubky-sdk/src/actors/pkdns.rs`) writes one.
2. The SDK tries each `_pubky` target in priority order, as PKARR's endpoint design specifies. Today `extract_host_from_packet` takes the first match.
3. A homeserver republishes a packet that lists it in any `_pubky` record. Today the user-key republisher (`src/republishers/user_keys_republisher.rs`) skips a packet whose first target is another homeserver.

Enrollment through Ring: the user picks alternates and gets a signup token from each operator (the homeserver default is `signup_mode = "token_required"`), Ring approves a `signup_grant` per alternate for the designated publisher's client key, and Ring signs one packet listing every enrolled homeserver. The designated publisher and the mirrors republish the last signed packet unchanged. Readers accept the newest signed packet from any carrier. Browsers resolve through a relay list that includes relays Synonym does not run.

**Gate:** with the primary's republisher stopped, the identity still resolves after the DHT would have dropped an unrepublished packet. A reader holding an old packet picks up the newer one from a mirror. A client without Slime reaches the alternate when the primary is unreachable.

## Phase 4. Author signatures at write time

**Job:** both. **Repos:** `pubky/pubky-homeserver` (SDK and homeserver), `pubky-app`, `pubky-app-specs`

The app key that writes a record signs its URI, content hash, and signing time. The homeserver stores the signature and the grant, and returns them with the record on GET and in the event stream. Readers verify offline: the grant's issuer is the author, its client key is the signer, its capabilities allow the path, and the signing time falls within the grant's validity. Follow the delegated-key design in progress in the Pubky team (Marcos's research) rather than a Slime-specific encoding; the reference fixtures use a provisional encoding of the same claims. Records written before this lands are re-signed by the author's app on its next write session.

The app admits a copy from anyone other than the author's own homeserver only with a valid author signature, and rejects unsigned or badly signed copies. §8.1's rule changes with it: a bearer session token never signs content, and a grant client key signs what its capabilities allow.

**Gate:** a forged listing among several copies is rejected, not shown. An enrolled homeserver cannot add a record the author did not sign. A record still verifies after its grant expires. The ported author-signature vectors pass.

## Phase 5. Replaceable indexers

**Job:** indexing. **Repos:** `pubky-app`, `pubky/pubky-nexus`

- `pubky-app`: `nexusUrl` (`src/libs/runtime-config/runtime-config.schema.ts`) becomes an ordered list with health-based failover.
- `pubky-nexus`: return each record's `content_hash` and author signature, so the app can check what the indexer served, and raise `monitored_homeservers_limit` above its default of 50.
- Ship at least one indexer and one PKARR relay that Synonym does not run as defaults.

An indexer's counts, rankings, and recommendations stay labeled as its claims.

**Gate, first part of the headline test:** Nexus is removed completely, and the app fails over to the second indexer with no manual edit. Search and discovery work through it. A record it serves without a valid author signature is not shown as the author's. A fresh install finds content through its default indexers alone.

## Phase 6. Signed indexer answers and static slices

**Job:** indexing. **Repos:** `pubky/pubky-nexus`, `pubky-app`

Indexers sign their answers to the four primitives (`slime-candidates/1`, signed with an indexer key that holds a grant from its operator), so omission and equivocation become provable. A reader with two indexers configured MAY cross-check reverse-edge queries.

Build the sharing controls and the slice: the app publishes a static signed slice of what the user chose to share at `pubky://<user>/pub/slime/slices/<n>/`, with author-signed records, on a schedule rather than on every change, keeping the latest few. Other users' slices import into the replica with the publisher recorded as supplier. Folder export and import use the same format.

**Gate, second part of the headline test:** Dana's homeserver goes dark. Alice opens Dana's shop, listings, and tags from Bob's slice and the indexer, every copy verified against Dana's signature, and searches them offline. Carol's new tag on a listing reaches Alice through the indexer. One indexer omits a tag and the other's signed answer exposes it. The slice lists exactly what the sharing choices select, and never the last-read marker, private favorites, private follows, trust marks, or searches.

## Phase 7. Publishing failover

**Job:** local fallback, for publishing. **Repos:** `pubky/pubky-homeserver`, `pubky-app`, `pubky-backup`

The designated publisher replicates every authored public record, with its author signature, to every enrolled homeserver. On persistent refusal, 3 failures across 10 minutes, or a primary that serves a version older than one it accepted, it switches to the next healthy enrolled homeserver with a verified copy and signs a home statement for mutable paths. It asks Ring to reorder `_pubky`, and the app says when that has not happened.

Mutable edits use the 0.13 lock on `/storage`: `storage.lock`, compare the ETag with the outbox row's base hash, `put_locked`, `unlock`. A mismatch leaves the row `conflicted`. Upstream asks: `If-Match` and `If-None-Match: *` on writes, and `ETag` exposed through CORS so web apps can run the compare. Until then web apps hand mutable edits to a companion.

**Gate, third part of the headline test:** Synonym's homeserver disables Alice's writes (`POST /users/{pubkey}/disable`) while serving stale reads. Alice's next post publishes on her alternate with no prompt, and Bob and Carol read it through her `_pubky` records. Her edits follow her home statement. The same holds when the primary times out instead. Ring was not contacted during the switch, and the app never held the identity seed. Two devices editing one listing while partitioned produce a conflict, not a silent overwrite.

## Phase 8. The headline test and its variants

**Job:** both. This is the final gate.

Run with real clients:

1. The headline test in the specification.
2. The seller's homeserver down, served from author-signed copies.
3. A forged listing among several copies, rejected.
4. The primary timing out, and separately serving stale data while refusing writes.
5. A fresh install finding content through default indexers alone.
6. Every participant on Synonym-operated homeservers.
7. Nexus down, with a second indexer restoring search.
8. The primary's republisher stopped, with the identity still resolving.

Nexus's hostnames resolve nowhere for runs 1, 5, and 7. Independence means separate operators and machines, not two hostnames on one backend.

## What each phase is allowed to claim

| After | Claim |
|---|---|
| 0 | Offline reading and composing for data already on the device. |
| 1 | The app answers from its own index, built from original records. |
| 2 | Followed keys, shops, and listings stay current and browse offline with their dependencies. |
| 3 | An identity lists several homeservers, and stays resolvable when one stops republishing it. |
| 4 | Every copy can be checked against its author. Forgeries are rejected. |
| 5 | Search survives losing Nexus. No indexer is required. |
| 6 | Indexer answers are accountable, and anyone can publish a signed slice. |
| 7 | Publishing fails over automatically within the enrolled homeservers, without the identity seed leaving Ring. |
| 8 | The headline test and its variants pass. |

## Deferred

| Work | Returns when |
|---|---|
| Live query providers and their advertisements | Someone wants to run one, after phase 6 |
| Crawling providers through `peers` lists | Live providers exist |
| Notices from unknown senders | Indexers prove unable to carry inbound activity |
| Home statements beyond the stale-primary case | A failure mode needs them |
| Sharing controls beyond "share what I follow" plus per-key choices | Users ask for them |
| Privacy and compliance layers | The base works |

## Not in this plan

| Work | Reason |
|---|---|
| A global index in the DHT, shared rankings, universal reputation | Indexers answer, each reader ranks locally. |
| A new key delegation mechanism | Slime keys are client keys of Pubky grants. |
| A shop, listing, or review schema | Slime indexes whatever records sellers publish. |
| Protection against state seizure or anonymity | Outside Slime's threat model. |
| A homeserver process in the browser | The replica is in-process storage. |

## Tests

Each phase lists the behavior that closes it. The Python checker covers what files can show: folders, author signatures and forged copies, detached JWS signatures, hostile archives, real pubky.app records and their ids, dependency chains and states, slices and their scopes, signed indexer answers, grants, services documents, home statements, merges over homeserver event streams, and the headline test's data path offline (`examples/test_headline.py`). It does not show indexer failover, offline boot, Ring grants, or homeserver acceptance. Those need real clients.
