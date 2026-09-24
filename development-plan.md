# Slime development plan

Slime is the replica and the folder. This plan builds both inside Pubky App. A **homeserver** is the host that stores a key's records. **PKARR** is the record that says which homeserver that key uses. The **replica** is original bytes plus local work on the device. **Exchange** is import and export of a folder of those records.

Use the existing SDK, homeserver event streams, PKARR, tags, Paykit, Locks, and `pubky-backup`. Do not open a new protocol repository until Exchange is in the App and a second implementation needs a shared crate.

Reference sets and a Python checker live in [examples/](examples/README.md). Port those vectors. They show folder integrity and merge behavior. They do not show that the App survives a restart or that a homeserver handles a conflict.

Read the current `pubky/pubky-app` sources for posts, session restore, and homeserver signup before editing.

## Phase 0. Durable workspace

**Repo:** `pubky/pubky-app`

Split local storage into workspace, record store, and derived index. A schema rebuild may drop the derived index only. Drafts, outbox rows, pins, and private settings survive.

An outbox row has a local operation id, account, target URI, intended bytes, dependency ids, known base version, and a state: `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, or `conflicted`. Persist the row and the bytes before the interface reports local success. If the homeserver throws, keep the row. Do not delete the local post.

Boot the installed app with the network blocked and with session refresh failing. Retained data still reads. New publication stays `blocked-auth` or `pending`.

Ship a private workspace export in this phase. It is a file the user saves. It is not a public set.

**Gate:** cold start with no network. Kill the process after queueing an action and see it after restart. Expire the session while offline and keep the work. Rebuild the derived index and lose nothing in the workspace.

**Stop if:** the fix needs the identity seed in the page. That belongs in Ring.

## Phase 1. An index built from originals

**Repos:** `pubky-app`, record schemas in `pubky-app-specs`

Store original bytes by origin URI and SHA-256. Build follows, tags, posts, and bookmarks from those bytes with the existing normalizers. The following feed lists retained authors' posts. It is not a saved list of indexer ids.

An indexer response may fill the record store only after the original fields are taken out. Anything the indexer added stays labeled as the indexer's claim. Never write an enriched indexer object back as if the author wrote it.

**Gate:** rebuild the index with the network blocked and recover the following feed, tags, and known replies. Do not attach a newer body to an older event hash.

## Phase 2. Exchange

**Repo:** `pubky-app`

Export a README, optional key and link lists, and `records/<author>/...` holding original bytes. Allow public record types only. Deny drafts, read state, searches, carts, orders, addresses, payment requests, tokens, and unlocked Lock content.

Import by staging, enforcing filename and size rules, previewing, then committing once. Offer separate choices to keep records, follow keys, refresh, and serve. Only "keep records" defaults on.

Port inventory and signature checks from the Python checker. Leave the signing control off until Phase 6. Keep unknown proof files as opaque bytes.

**Gate:** reimport is idempotent. Two paths with the same bytes and different origins stay two origins. A public export contains no private orders. A tampered signed file fails. A hostile ZIP (path traversal, link, duplicate names) never escapes the staging directory.

## Phase 3. Collection from selected homeservers

**Repos:** `pubky-app`, the SDK in `pubky-core`

For keys the user follows or pins, resolve the homeserver with the SDK and read scoped events. Group keys by host. Keep one cursor per provider and scope. Persist the event before advancing the cursor. Reconcile after a suspected reset. Do not share a cursor with Nexus.

Fetch metadata and text first. Media is on demand, in its own budget. Start here, then measure: no automatic graph expansion, 4 requests in flight, 2 per host, a 128 MiB text target, public serving off.

Collect the selected scope during ordinary use, so an indexer outage is not the first time those records are fetched.

**Gate:** with every large indexer blocked, selected homeservers still refresh. A known record missing from an index response is not shown as deleted. A crash between ingest and body fetch leaves a pending fetch. An old cursor is not reused after a homeserver move.

Time fixtures of 50, 250, and 2,500 authors on a phone. If the phone cannot hold the large set, the app asks for a companion instead of evicting pins.

## Phase 4. The local index answers first

**Repo:** `pubky-app`

Every read checks the local index and returns those hits before any network call. After that, `getOrFetch` tries peers who hold that familiar key, then the author's homeserver, and only then the user's preferred indexer. Until Phase 5, no peer is serving, so that middle step is empty and the path is local index, then homeserver, then indexer. The indexer fills coverage outside the familiar scope, and familiar gaps nobody else answered. A local hit does not contact Nexus. If Nexus omits a record, try the direct path. Do not write a tombstone. Indexer-added scores and ranks stay labeled as the indexer's claims and are not stored as author records.

In the detail view, show local retention, publication acceptance, and indexer visibility as separate fields.

**Gate:** with Nexus blocked, a retained author and a directly readable homeserver record still appear, with no manual endpoint edit. A feed open with the records already local produces no indexer request. A provider hint cannot receive a private query.

## Phase 5. Familiar keys keep the mesh dense

**Repo:** `pubky-app`

Familiar keys are follows, keys marked trusted, and sellers of shops or listings the user follows. The familiar scope is their public posts, follows, tags, shop records, and listings, plus public tags whose target the user already keeps, plus public listings the user has publicly bookmarked.

On each ordinary session, refresh that scope from homeservers and from peers that already hold the bytes. Serve the public familiar records this device holds when a peer asks by key or by record URI. Default is on. Settings can turn serving off, or turn fetch and serve off. Asking is not a search broadcast. Do not send queries, drafts, orders, private favorites, or indexer scores.

A private favorite pins the public shop and its listings locally and fetches them into the local index. The pin is not served and does not make that seller a familiar key. A peer who names that listing's URI can receive the public bytes, with no favorite flag. A served tag keeps its author. The recipient does not follow that author and does not gain a second copy of the claim. Followed shops, publicly bookmarked listings, and their tags replicate as those public records. Paykit still starts only when the user buys. A Lock still gates locked bytes, which are not served.

Phase 3 leaves serving off. This phase turns the familiar default on.

**Gate:** two clients follow the same seller. Nexus and the seller's homeserver are blocked for client B. Client A already holds the seller's tags, shop record, and listings. Client B asks A by that seller's key, fetches those records, and searches them in B's local index with the network blocked. A's private favorite pin, A's last search, and any indexer score or rank are absent from what B received. A seller that A only privately favorited is not returned when B asks which keys A will serve. Naming that listing's URI still returns the public listing bytes and nothing that marks it as a favorite. Reimporting the tag does not duplicate it. A third client that follows nobody does not receive the shop just by being online.

## Phase 6. Optional signature on a set

**Repos:** `pubky-app`, Pubky Ring

Sign the `slime/set/1` message through Ring or another isolated signer. No seed in the App. Show the signing key. Reject a set signature offered as a record proof or a payment proof.

Author signatures on records stay opaque until Pubky has a content-signature format. Do not invent one here.

**Gate:** a second implementation, starting with the Python checker and then a Rust or Ring vector, detects a changed file, README, or origin mapping, and accepts an unchanged folder after recompression.

## Phase 7. Catalogs, then Paykit

**Repos:** `pubky-app`, the repo that owns listing records, `paykit-rs`, `pubky-locks`

Name the deployed listing schema and its owner before rendering prices or stock. Until then, shop-like records stay opaque.

When the schema exists, the adapter reads seller, listing id, variants, price unit, availability, and media refs from native fields. Tags stay tags: a claim by one key about a target. Local filters run with the network blocked.

Buy hands the seller and the offer reference to Paykit. Paykit checks the live counterparty, the terms, and the payment request. A Lock applies only when the record is access-gated. The folder does not reserve stock, does not add quantity when a listing is copied, and does not revive a withdrawn listing from an older catalog.

**Gate:** a packet capture while browsing a catalog shows no analytics, no remote images, and no quote request.

## Phase 8. A companion for larger copies

**Repo:** `pubky-backup`, plus a thin App client

Use the backup core to sync keys and snapshot the record store, and to hold an encrypted workspace backup when the user asks for one. The companion serves only enabled public scopes, to authorized App origins, on a restricted bind address. It is not a public homeserver, and PKARR does not point at it by default.

The App works without the companion. The companion is how a large media scope and a second device get a copy.

**Gate:** import on a second origin. A restore preview does not overwrite a live namespace. The companion receives the private workspace only when that backup was turned on.

## Phase 9. Conditional writes, then a second public copy

**Repos:** homeserver, SDK, then `pubky-app`

This phase waits on a server operation:

`apply(operation_id, origin, expected_version_or_absent, action, body)`

The same operation id returns the same outcome. A version mismatch conflicts and does not write. A delete leaves enough history that an older queued PUT cannot bring the object back. A client GET followed by PUT does not qualify.

After that operation is tested, a user may enroll a second homeserver as a copy of authored public records. Repair runs from the device or companion that holds the bytes, not by asking the failed primary to push. Private backups go to a different destination.

Moving the publishing location in PKARR stays a Ring action. The App can say "the alternate has the bytes, the public address still names the old home."

**Gate:** two devices edit one listing while partitioned, and neither silent last-write nor a doubled stock count wins. A replica that returns with stale edits does not overwrite an accepted successor. A crash after the local commit and before network acceptance keeps the right per-destination state. Repair reports incomplete protection until the extra copy verifies.

## Not in this plan

| Work | Reason |
|---|---|
| An inbox for unknown senders | Watching selected authors does not need one. A reply from a stranger is a coverage gap. |
| A homeserver process in the browser | The replica is in-process storage. |
| A torrent client in the app | Folder, ZIP, and HTTP are the interchange. |
| Automatic PKARR failover | The App must not hold the identity seed. |
| Running an imported recipe | A preference is data. |
| A listing schema owned by Slime | Adapters follow the records that already exist. |

## What each phase is allowed to claim

| After | Claim |
|---|---|
| 0 and 1 | Offline reading and composing for data already on the device. |
| 2 | People can exchange a folder of attributed records. |
| 3 and 4 | A selected scope survives losing Nexus. The local index is the first read. |
| 5 | People who follow the same keys keep each other's public posts, tags, shops, and listings available. Private favorites stay private. |
| 6 | The exporter of a folder can be authenticated. Authorship is separate. |
| 7 | A public catalog can be searched locally. Buying is Paykit. |
| 8 | A second device or a companion can hold the replica. |
| 9 | Mutable edits are safe across a replica. The public homeserver address moves only when Ring signs that move. |

Phase 0 alone is not Slime. Phases 0 through 8 are not automatic publishing failover.

## Tests

Each phase lists the behavior that closes it. An import mock does not close offline boot. The Python checker does not close Ring signing or familiar-key serving. Independence means two isolated services, not two hostnames on one backend.

Phase 4's test is a retained feed opened with Nexus blocked: the local index answers, and the client makes no indexer request. Phase 5's test is the two-client gate above: B reads A's copy of a followed seller's tags, shop, and listings, and does not receive A's private favorite, search, or indexer scores.

The rules those tests enforce are in the [specification](spec.md). The product promise is in the [brief](brief.md).
