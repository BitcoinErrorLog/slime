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

The app admits a copy from anyone other than the author's own homeserver only with a valid author signature, and rejects unsigned or badly signed copies. A bearer session token never signs content, and a grant client key signs only what its capabilities allow ([specification section 2.1](spec.md#21-records-and-author-signatures)).

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
| 5 | Search survives losing Nexus. No single indexer is required. |
| 6 | Indexer answers are accountable, and anyone can publish a signed slice. |
| 7 | Publishing fails over automatically within the enrolled homeservers, without the identity seed leaving Ring. |
| 8 | The headline test and its variants pass. |

## Milestones

Build one Rust crate, `slime`, on the Pubky SDK 0.13 and `pubky-app-specs` 0.8.1, and use it everywhere: a command-line tool and viewer for the demo, a WASM build for web, UniFFI bindings for iOS and Android, and a reference indexer. The phases above are the work inside `pubky-app` and the Pubky services. The milestones below order that work with the crate, the demo, and the other clients.

| Milestone | Work | Gate | Depends on |
|---|---|---|---|
| M0. Decisions | Where the crate lives, the `pubky-homeserver` issues (several `_pubky` records, author signatures, `If-Match`, `ETag` in CORS), the author-signature encoding agreed with Marcos, the grant-lifetime ask, the pubky-app workspace ADR, the indexer-list change. Vectors extracted from the Python checker. | The upstream asks are filed and the ADR is accepted. Vectors run in Python CI. | None |
| M1. Demo | `slime` core, CLI, minimal indexer, homeserver branch, simulator grants, viewer | The recorded headline run on `pubky-testnet`, reproducible with `make demo` | M0 |
| M2. Developer preview | npm package, full reference indexer, Nexus changes, conformance CI, quickstart, template, agent skill | The developer-preview gate in M2 below | M1 |
| M3. Web | `pubky-app` phases 0 to 7 | The gates of phases 0 to 7 | M2, the workspace ADR, author signatures and several `_pubky` records merged and released |
| M4. Desktop companion | `pubky-backup` extension | Companion replicates, republishes, publishes slices, and fails over on testnet | M2 |
| M5. Ring and mobile | Ring enrollment UX with signup tokens and the multi-homeserver packet, `react-native-slime`, mobile client integration | Enrollment on a real device. Failover without the seed leaving Ring. | Several `_pubky` records merged and released |
| M6. Headline on real infrastructure | Independent operators, Nexus removed, the phase 8 run with its variants | Phase 8 passes | M3, M4, M5 |

## Blockers and upstream asks

| Blocker | Why it matters | Owner | Way through |
|---|---|---|---|
| **Records carry no author signature.** A homeserver stores bytes written under a session. Nothing a reader receives proves which key wrote them, so a copy from anyone but the author's homeserver cannot be checked. | Without it, slices and indexer copies cannot be trusted when the author's homeserver is down, and a forged listing cannot be told from a real one. | Pubky Core engineer, with Marcos | The app key that writes a record signs its URI, content hash, and signing time. The homeserver stores the signature and the grant and returns them on GET and in the event stream. Follow the delegated-key design in progress rather than a Slime encoding. The reference fixtures use a provisional encoding of the same claims, replaced when the design lands. |
| **PKARR packets list one homeserver in practice.** The SDK writes one `_pubky` record (`build_homeserver_packet` in `pubky-sdk/src/actors/pkdns.rs`) and reads the first (`extract_host_from_packet`). A homeserver republishes a user's packet only when its first `_pubky` target is that homeserver (`src/republishers/user_keys_republisher.rs`). | Readers cannot find the alternates from the identity's own record, and alternates skip republishing a packet that names the primary first. A primary that bans a user and stops republishing makes the user unresolvable within hours. | Pubky Core engineer, Ring engineer | Three small changes: publish several `_pubky` records, try each in priority order (PKARR's `design/endpoints.md` already specifies this), and republish packets that list the homeserver anywhere. Until then, the designated publisher and mirrors republish the last signed packet unchanged, publishing fails over, and other readers follow once Ring moves `_pubky`. |
| **pubky-app has one indexer URL.** `nexusUrl` in `src/libs/runtime-config/runtime-config.schema.ts` is a single string. Nexus monitors at most 50 homeservers by default (`monitored_homeservers_limit`). | Losing Nexus loses search. An indexer that stops at 50 homeservers misses independent sellers. | Web engineer, Nexus engineer | An ordered indexer list with health-based failover, shipped with at least one indexer and one PKARR relay that Synonym does not run. Raise the Nexus limit. |
| **pubky-app's local database is a cache by decision.** ADR-0019 (accepted 2026-09-15) deletes and recreates it on any schema version mismatch. | A workspace or outbox inside it is wiped at the next schema change. | Web lead | A pubky-app ADR that keeps the workspace and record store in a separate IndexedDB database with versioned migrations, outside the recreate path, amending ADR-0001. |
| **Alternates need signup tokens.** The homeserver default is `signup_mode = "token_required"`. | Enrolling an alternate needs a token from its operator before Ring can approve the `signup_grant`. | Ring engineer, operators | Enrollment asks each operator for a token, and the app shows which alternates are open, token-gated, or closed. |
| **Grant revocation is invisible to readers, and grants last two years.** Revocation lives on each homeserver and only the owner's sessions can list it. The SDK's default lifetime is two years (`DEFAULT_GRANT_LIFETIME_SECS`), and grant deep links carry no lifetime parameter. | A record signed while its grant was valid stays valid by design. A revoked slice, indexer, or failover key's later signatures verify until the grant expires. | Pubky Core engineer, Ring engineer | Ask for a requested lifetime on grant links, or a public revocation status per grant. Until then, readers prefer copies from the identity's own homeservers, and slice, indexer, and failover keys hold only the capabilities they need. |
| **Mutable edits need the `ETag`, and web apps cannot read it.** The homeserver's lock does not accept `If-Match` (`routes/tenants/lock.rs` lists entity tags as not provided), and its CORS configuration does not expose `ETag`. | Mutable edits take three round trips (lock, compare, locked write), and a web app on another origin cannot run the compare. | Homeserver engineer | Ask for `If-Match` and `If-None-Match: *` on `PUT` and `DELETE` (RFC 9110), and for `ETag` in the exposed CORS headers. Until then, web apps hand mutable edits to a companion. |

## M1. The smallest convincing demo

**What it shows, in one scripted run:**

1. Four identities on `pubky-testnet`: Alice, Bob, Carol, and Dana, plus Mallory for the forgery. There are three homeservers: a primary standing in for Synonym's, which Alice, Bob, and Carol use, Alice's alternate, and Dana's own. Two indexers run under two operator identities, one standing in for Nexus. Alice's PKARR packet lists her primary and her alternate as `_pubky` records.
2. Dana publishes pubky.app records: a profile, two posts used as listings, and an image post whose file record points at its blob. Her app key, granted through the simulator, signs each record at write time, and her homeserver serves the signature with it. Bob follows Dana and chooses to share Dana's key. His slice key holds a grant with write on `/pub/slime/`, and he publishes a signed slice to his homeserver.
3. The Nexus stand-in is stopped. Alice's app fails over to the second indexer with no manual edit. Its signed answers to `author(Dana)` and `label` verify, and so does Dana's signature on every entry.
4. Dana's homeserver is stopped. Alice opens Dana's shop, listings, and image, through the post, file, and blob chain, from Bob's slice and the indexer. Then the network is cut and she searches them offline. A copy of one listing with a different price, signed under Mallory's own grant, is offered to her and rejected.
5. Carol tags a listing. Alice finds the tag through the indexer's signed `refs` answer.
6. The primary disables Alice's account for writes through its admin API and keeps serving stale reads. Alice posts. Her client publishes to the alternate and signs a home statement. Bob reads the post through Alice's `_pubky` records. The primary's republisher is stopped, and Alice still resolves because her client and a mirror republish her packet.
7. Every step prints what was verified: grants, author signatures, signatures on Slime documents, content hashes, ids, and scopes. At the end the harness greps all traffic for Alice's searches, favorites, unshared records, and last-read marker, and finds none.

**What to build it on:**

| Part | Built on | Notes |
|---|---|---|
| `slime` crate (core) | Rust, `pubky` 0.13, `pubky-common` (grants and JWS), `pubky-app-specs` 0.8.1, `blake3`, `jsonschema` | Slime document types, detached JWS, grant checks, author-signature verification, entry derivation over `pubky-app-specs` types, the four primitives over SQLite, the event-stream merge, dependency states, slices, signed-answer verification, home statements. A port of the Python checker, passing its vectors. |
| `slime-cli` | The `slime` crate, `pubky-testnet` with embedded Postgres | `slime share`, `slime slice publish`, `slime slice import`, `slime query`, `slime verify`, `slime enroll`, `slime post`, and `slime resolve`. One scripted run is the demo. |
| `slime-indexer` (minimal) | Rust, axum, SQLite | Reads the testnet homeservers' event streams, answers the four primitives with signed answers, and returns every record's content hash and author signature. Two instances under two operators. |
| Homeserver branch | A branch of `pubky/pubky-homeserver` | The three multi-homeserver PKARR changes, and author signatures stored and served on GET and in the event stream in the provisional encoding. With tests, as the proof for the upstream pull requests. |
| Grants | `pubky-ring-simulator` | App-key, slice-key, indexer-key, and failover-key grants, and the multi-homeserver packet, signed as Ring would |
| Viewer | `pubky-app-templates` Vite starter, with `@synonymdev/slime` (WASM) or a local HTTP bridge to the CLI | Alice's replica: shop, listings, tags, dependency states, and verification results, with a visible offline switch |

**How long:** about 10 to 13 engineer-weeks, or 5 to 7 weeks for two engineers.

| Work | Estimate |
|---|---|
| `slime` crate core, reusing `pubky-common` for JWS and grants and `pubky-app-specs` for record types, and passing the Python vectors | 3.5 to 4.5 weeks |
| Multi-homeserver PKARR: SDK publish and iterate, republisher change, tests | 1.5 to 2.5 weeks |
| Author signatures on the homeserver branch: store, serve on GET and in events, sign in the SDK's write path, tests | 1.5 to 2 weeks |
| Minimal indexer with signed answers | 1 to 1.5 weeks |
| CLI and scripted run on `pubky-testnet` | 1 week |
| Viewer | 1 week |
| Integration, forgery and failover scripts, recording | 0.5 to 1 week |

Assumptions: the demo runs on SDK 0.13 in Rust and does not touch `pubky-app` or Nexus, so the ADR-0019 question and the Nexus changes do not gate it. The Nexus stand-in is a `slime-indexer` instance. The simulator can sign a packet with several `_pubky` records and grants for arbitrary client keys, or gains that in a day. The author-signature encoding is the provisional one, swapped for the delegated-key design when it lands. Account refusal uses the existing admin endpoint. No mobile and no desktop companion. If the multi-homeserver branch slips, the demo still shows failover of publishing and reading, with the reader following the alternate after the simulator moves `_pubky`.

**Deliverable of M1:** a recorded run and a `make demo` target that anyone can reproduce with Rust alone.

## M2. The developer offering

| Component | Contents | Owner by role |
|---|---|---|
| `slime` crate | Types for every Slime document. Detached JWS, grant checks, and author-signature verification through `pubky-common`. Entry derivation through `pubky-app-specs`, plus schema-agnostic references for other records. A `Replica` trait with SQLite and in-memory stores. The four primitives. The event-stream merge. Dependency states and chains. Slice export, import, and publishing. An indexer client with an ordered list, health, and signed-answer checks. Sync loops over `pubky` event streams. The read-order router. The home-statement resolver. Locked mutable writes. | Rust SDK engineer |
| `@synonymdev/slime` (npm) | A `wasm-bindgen` build of the crate, packaged like `@synonymdev/pubky` and `pubky-app-specs`, with an IndexedDB store in its own database. Grant client keys can stay non-extractable in WebCrypto, through the SDK's delegated proof-of-possession signer. | Rust SDK engineer, web engineer |
| Native bindings | UniFFI following `pubky-core-ffi`: Swift Package, Android AAR, and `react-native-slime` following `react-native-pubky`. | Mobile engineer |
| Conformance suite | Language-neutral vectors (`vectors/*.json` with expected verdicts) generated from the Python checker's fixtures and negative cases, all over real, author-signed pubky.app records, including forged and unsigned copies. The Python checker stays the reference runner. The Rust crate, the WASM build, and any third-party implementation run the same vectors in CI. | Protocol engineer |
| Reference indexer | `slime-indexer`: axum, SQLite for a single operator, Postgres for hosted use. Follows homeserver event streams, answers the four primitives with signed answers, returns author signatures, and enforces limits. Ships as a Docker image and an Umbrel app (Pubky already has `umbrel-app-store`), so operators other than Synonym can run defaults. | Rust SDK engineer |
| Nexus changes | Content hashes and author signatures on every record it returns, signed answers to the four primitives under an indexer key granted by Synonym's identity, and a higher `monitored_homeservers_limit`. Nexus then sits in the indexer list like any other. | Nexus engineer |
| Docs | A quickstart on `pubky-testnet`: sign and publish, configure two indexers, publish and import a slice, verify. Guides for "Add Slime to a web app" and "Run an indexer". An API reference from rustdoc and TypeDoc. The spec published on `pubky-knowledge-base-v2`. | Developer advocate |
| Examples | A template in `pubky-app-templates` that browses a shop offline and rejects a forged listing. The demo CLI script. | Developer advocate |
| AI tooling | A Slime skill in `pubky/agent-skills`, so coding agents use the crate and vectors correctly. | Developer advocate |

Gate for a developer preview: the vectors pass in Rust, WASM, and Python. The quickstart runs from a clean machine. The indexer image passes the Indexer conformance level. The template app works with the network cut.

## Platforms

| | Web (`pubky-app`) | Desktop (`pubky-backup`, Tauri) | Mobile (React Native, the Ring stack) |
|---|---|---|---|
| Replica | Workspace and record store in their own IndexedDB database with versioned migrations, outside the Dexie cache that ADR-0019 recreates. The cache stays a cache and is filled from the replica. | SQLite through the native `slime` crate | SQLite through `react-native-slime`. MMKV only for small settings. |
| Sync loops | A dedicated Web Worker running `@synonymdev/slime`, foreground-only. The Serwist service worker keeps serving app assets offline. | Native Rust threads, running while the app is open or in the tray | Foreground sync, plus opportunistic background tasks |
| Background limits | Runs only while a tab is open. Periodic Background Sync exists only on Chromium for installed PWAs. Safari can clear script-written storage for sites not added to the home screen after 7 days without use. Call `navigator.storage.persist()`, and show storage state. | None beyond the OS. It can run as a login item. | iOS: `BGAppRefreshTask` runs at the system's discretion, for short windows. Android: WorkManager, with a 15-minute minimum period and Doze deferrals. Event streams and slices are drained on open. |
| Slices | Publishes static slices to the user's homeserver on a schedule | Same | Same |
| Republishing the user's PKARR packet | While open | Continuously | On open and in background tasks |
| Failover key and designated publisher | Possible: the grant client key kept non-extractable in WebCrypto. It detects refusal only while open. | Best fit: the grant client key in the OS keychain (macOS Keychain, Windows Credential Manager, libsecret). Online most of the time. | Workable: Keychain with device-only access on iOS, Android Keystore on Android. Refusal is detected at publish time. The Secure Enclave does not hold Ed25519 keys. |
| App key (author signatures) | The grant client key the app writes with, non-extractable in WebCrypto | The companion's grant client key, in the OS keychain | Keychain or Keystore |
| Slice key | A grant client key with write on `/pub/slime/` | Same, in the OS keychain | Same, in Keychain or Keystore |
| Identity key | Ring only | Ring only | Ring only |

One designated publisher per account. When a desktop companion exists, it is the designated publisher, and the web and mobile apps hand it their outbox. Without a companion, the device the user publishes from holds the failover key.

### Desktop companion: `pubky-backup`

`pubky-backup` already keeps local copies of users' data, so extend it into the Slime companion:

1. Embed the `slime` crate.
2. Replicate the user's authored records, with their author signatures, to every enrolled homeserver, and republish the user's PKARR packet.
3. Hold the failover key and act as designated publisher, including mutable edits for web apps.
4. Publish the user's slices on a schedule.

It also carries the encrypted workspace backup to `/priv/`. Owner: desktop engineer.

### Mobile

Ship `react-native-slime`. Then add a Slime layer to the Pubky mobile client: local replica, author signatures on writes, the indexer list, sharing controls, slice publishing, and failover at publish time when there is no companion. Ring runs enrollment: a signup token and a `signup_grant` approval for each alternate, and one PKARR packet listing every enrolled homeserver. Owners: mobile engineer, Ring engineer.

## Roles

| Role | Scope |
|---|---|
| Protocol engineer | Spec upkeep, vectors, conformance levels, reviews of every implementation |
| Rust SDK engineer | `slime` crate, WASM and UniFFI builds, reference indexer |
| Pubky Core engineer | Several `_pubky` records in the SDK and republisher, author signatures with Marcos, grant lifetime or revocation status |
| Homeserver engineer | `If-Match` and `If-None-Match` on writes, `ETag` in CORS |
| Ring engineer | Enrollment UX, signup tokens, the multi-homeserver packet, simulator support |
| Web engineer | The workspace ADR and `pubky-app` integration |
| Desktop engineer | `pubky-backup` companion |
| Mobile engineer | `react-native-slime`, mobile client integration |
| Nexus engineer | Content hashes, author signatures, and signed answers from Nexus, and the homeserver limit |
| Developer advocate | Quickstart, guides, templates, agent skill, knowledge-base pages |

The demo needs the Rust SDK engineer and one Pubky Core engineer. Every later milestone reuses the crate the demo produced.

## What this builds on

| Piece | Where | What Slime uses |
|---|---|---|
| Pubky SDK 0.13.0 (2026-09-23) | `pubky/pubky-homeserver` (`pubky-sdk/`), crate `pubky`, npm `@synonymdev/pubky` | PKARR resolution, grant sessions, path-addressed `/storage`, WebDAV `lock`, `put_locked`, and `unlock`, event streams with BLAKE3 `content_hash` |
| Grants | `pubky-common/src/auth/grant.rs` and `auth/jws.rs`, homeserver `client_server/auth/grant/` | Every Slime signing key: a `pubky-grant` JWS binds a client key to capabilities and an expiry, verified offline. The app key that writes a record signs it. JWS helpers for Slime's detached signatures. |
| Record schemas | `pubky/pubky-app-specs` 0.8.1 (crate and npm) | Entry adapters and id rules for profile, post, follow, mute, tag, bookmark, feed, file, blob, and `last_read` |
| Mobile SDK | `pubky/pubky-core-ffi` (UniFFI), `pubky/react-native-pubky` (npm `@synonymdev/react-native-pubky`, used by Ring) | The pattern for native bindings |
| Local test network | `pubky-testnet` in `pubky/pubky-homeserver`: `EphemeralTestnet::builder().with_embedded_postgres()`, then `create_random_homeserver()` or `create_random_homeserver_with_config()` per homeserver. The lower-level `Testnet` also has `create_homeserver()`. | The demo harness and CI, with no Docker Postgres |
| Account refusal | Homeserver admin API `POST /users/{pubkey}/disable`: writes return 403 "User is disabled" and reads keep working | The demo's censoring primary, with no new code |
| Web app | `pubky/pubky-app`: Next.js 16, Dexie 4, Serwist, React Query, zustand. It pins `@synonymdev/pubky` 0.11.0 and `pubky-app-specs` 0.7.0. ADR-0001 (local-first writes), ADR-0003 (streams as caches), ADR-0019 (recreate the Dexie database on any version mismatch). | The replica host on web, after the workspace ADR |
| Desktop | `pubky/pubky-backup`: a Tauri app that keeps a local copy of users' published data | The desktop companion and designated publisher |
| Ring | `pubky/pubky-ring` 0.0.32: React Native 0.86, `react-native-keychain`, MMKV. Handles `signin_grant` and `signup_grant` links. Signs and republishes the identity's PKARR packet. | Grants for app, slice, indexer, and failover keys, enrollment, the multi-homeserver packet |
| Ring simulator | `pubky/pubky-ring-simulator`: approves grant sign-ins against a local stack (SDK 0.12 and later) | Grants during the demo and development |
| Private storage | Homeserver `/priv/` paths, readable and writable only by a matching session (`docs/PRIVATE_STORAGE.md`) | Encrypted workspace backup. The homeserver admin can read `/priv/`, so encrypt on the client. |
| Nexus | `pubky/pubky-nexus`: watcher plus service over multiple homeservers, `monitored_homeservers_limit = 50` by default | The first of several replaceable indexers, returning content hashes, author signatures, and signed answers |
| Starters and tooling | `pubky/pubky-app-templates` (Vite starter), `pubky/agent-skills`, `pubky/pubky-knowledge-base-v2` (Astro) | Developer examples, AI coding skills, docs site |
| Reference | This repository: spec, schemas, Python checker, and tests over real, author-signed pubky.app records | The source for conformance vectors |

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
