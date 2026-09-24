# Slime specification

Slime is how a Pubky client keeps original records and passes them to someone else as files. A **homeserver** stores a key's records. **PKARR** publishes which homeserver that key uses. The **replica** is the device's copy of original bytes, local work, and the evidence of where each copy came from. **Exchange** is the folder format below. The specification adds no identity system, record type, payment rail, or inbox.

Requirements use MUST, SHOULD, and MAY.

Two conformance levels:

- **Exchange.** Import and export the folder. Preserve provenance. Follow the merge and disclosure rules.
- **Replica.** Exchange, plus a durable local workspace, an index built from retained originals, collection from familiar keys, and serving of those public records to peers. A remote indexer adds coverage. It is not the first read.

A client MUST say which level it implements. Replica does not require signatures or torrents. Fetching and serving the public familiar scope is part of Replica. It is on unless the user turns it off.

## 1. Records

A logical record is `pubky://<author>/<path>`, checked with the existing SDK. The author key is not the homeserver hostname and not the key of whoever supplied the copy.

A retained version is the origin URI plus the SHA-256 of the exact original bytes. Identical bytes MAY share a blob. Origin mappings MUST stay distinct. This digest MUST NOT replace native Pubky IDs or the native BLAKE3 content hash.

Three stores, even when one database holds them:

| Store | Holds | Rule |
|---|---|---|
| Workspace | Drafts, the outbox, read state, private settings, carts, orders | Session failure MUST NOT erase it. It is not a cache. |
| Record store | Original bytes, origins, proofs, source notes, deletion evidence | Normalization MUST NOT rewrite these bytes. |
| Derived index | Feeds, tags, catalogs, local search | Rebuildable. A provider's counts and scores stay labeled as that provider's claims. |

Unknown application types MAY be stored as opaque bytes. They MUST NOT be read as another type.

## 2. Folder

A set is a directory. ZIP, HTTP, and removable media carry the same directory. A torrent MAY carry one immutable snapshot later. Exchange does not depend on it.

```text
<set>/
    README.md
    keys.txt
    links.txt
    records/<author-key>/<path under that key>
    media/
    history/
    proofs/
    set.json
    set.sig.json
```

`README.md` SHOULD be present. `keys.txt`, when present, has one canonical z-base-32 public key per line. `links.txt`, when present, has one URI per line. A line whose first non-whitespace character is `#` is a comment. Importers MAY trim ASCII whitespace on list lines. They MUST NOT rewrite a file whose digest is being checked.

Under `records/<author>/`, the path is the claimed origin. That claim is the exporter's until the reader accepts the source or an author proof checks out. If the path is ambiguous, the importer MUST NOT guess from the file contents.

When a source path is unsafe as a filename, the exporter MUST use a generated safe name and an `origin` field in `set.json`. It MUST NOT change the logical URI quietly.

The README SHOULD say what was selected and whether linked pages were included. Clients MUST render it with scripts, remote embeds, and active HTML disabled. README text MUST NOT change follows, trust, budgets, signing, or serving, and MUST NOT start a tool.

## 3. Inventory and signature

`set.json` is format `slime-set/1`. It lists every payload file once, in ascending ASCII path order, with the exact byte length and lowercase hex SHA-256. The only root files left off the list are `set.json` and `set.sig.json`. Optional `origin` MUST match a recognized record path. Optional `created_at` is the exporter's UTC time, not the author's. Optional `previous` is `sha256:<digest>` of an earlier `set.json` from this exporter. It does not edit the authors' records and it does not delete anything.

Verifiers hash the exact `set.json` bytes they received. They MUST NOT parse and re-serialize before hashing. Duplicate keys, invalid UTF-8, a leading byte-order mark, non-finite numbers, and unknown fields in a version-1 object MUST be rejected.

`set.sig.json` is format `slime-signature/1`, purpose `set`, algorithm `Ed25519`. The signed message is the ASCII bytes of `slime/set/1`, one zero byte, then the 32-byte SHA-256 of the exact `set.json`. The signature is 64 bytes, unpadded base64url. The `signer` field is a canonical Pubky public key.

That signature means this key committed to this inventory. It MUST NOT be accepted as authorship of a record, a session grant, a PKARR update, or a payment.

Signing MUST use an isolated signer such as Pubky Ring. The tool MUST NOT ask for a mnemonic or put an identity seed in the archive, the page, or a peer process. A homeserver access grant MUST NOT be used as a content-signing key. A separate export key MUST be shown as that key.

A bad advertised signature MUST quarantine the import. It MUST NOT be accepted as an unsigned folder from a trusted sender. A valid signature with missing bodies is an authenticated inventory, not a complete set. Files absent from the inventory MUST NOT enter a verified set.

Version-1 names use ASCII letters, digits, `_`, `-`, `.`, and `/`. Each segment is 1 to 128 bytes. The full relative path is at most 512 bytes. Reject absolute paths, empty segments, `.` and `..`, backslashes, control characters, drive prefixes, percent-decoding, segments that end in a dot, Windows device names, and names that collide if case is ignored. Reject archive links, device entries, and duplicate names. Stage the archive before activating it. Never extract into the live account directory.

Parsing ceilings: `set.json` 16 MiB and 100,000 entries, signature file 8 KiB. A client MAY set a lower budget and MUST fail in the open when it does.

## 4. Import, collection, and publication

Import is staged and idempotent. It MUST NOT publish under the receiver's key, follow imported keys, pay, or change policy. Importing a folder MUST NOT add its authors to the served set. A record is served only when it is already in the public familiar scope. Importing the same bytes again MUST NOT create a second post, follow, or tag. Store original bytes before building any normalized view.

Collection preferences stay on the device unless the user exports a description of them. Opening a record MUST NOT add it to the served set unless it is already a public familiar record. A private read MUST NOT start serving.

One pipeline accepts folders, the chosen indexer, and direct homeserver reads. Each adapter keeps its own cursor, bound to that provider and that scope. A cursor MUST NOT be reused between Nexus and a homeserver, or after a suspected reset. Persist the event, and any pending body fetch, before moving the cursor forward. A newer body at a path MUST NOT be attached to an older event's hash. Directory order is not time order. Event positions that can exceed JavaScript's safe integer range MUST be stored as decimal strings.

Four absences stay distinct: the source is unavailable, the client has not looked, the source reports the record gone, and an authenticated deletion. An indexer's omission is never an author deletion. Dropping a record from a personal scope is a retention choice, not an author deletion.

Fetchers MUST limit URL schemes, refuse local and metadata addresses unless the user allowed them, check redirects, cap response size, and MUST NOT send one origin's credentials to another. Keys and links in an import are not permission to crawl.

Publication states are `pending`, `publishing`, `published`, `retryable`, `blocked-auth`, and `conflicted`. Persist the operation and the bytes before the interface reports local success. The homeserver's acknowledgment is the publication receipt. The indexer's acknowledgment is not. A retry may repeat a source event for the same bytes. The client deduplicates what it shows and MUST NOT promise that the server ran the operation once.

Until the homeserver has a tested conditional write, the client MUST NOT replay an edit or a delete onto a mutable path after a disconnect. It keeps the pending change and asks the user to rebase. A GET followed by a PUT is not a conditional write. New records with stable paths MAY be retried by one designated publisher.

Logout and an explicit wipe are user actions. A network failure is not.

## 5. Familiar keys

A key is **familiar** when the user follows it, marks it trusted, or it is the seller of a shop or listing the user follows. A trust mark is a local policy. It is not itself a shared record, and it is not an endorsement.

A record is in the **familiar scope** when any of these is true:

- A familiar key authored it, and it is public. This includes posts, follows, tags, shop records, and listings.
- It is a public tag whose target the user already keeps.
- It is a public shop record or listing for a seller the user follows, or for a listing the user has publicly bookmarked.

A private favorite is a workspace pin on a public shop or listing. It MUST cause the client to fetch and retain that public shop record and its public listings, and to index them locally. It MUST NOT be exported, announced, or served. The client MUST NOT add that seller to the familiar-key set because of the pin alone, and MUST NOT answer a request for a list of favorites. If a peer names that listing's URI, the client MAY return the public listing bytes, with the author unchanged, and without any field that says the listing was a favorite. If the user publishes a follow or a public bookmark, that published record is in the familiar scope and is shared like any other public record.

The default is on. The client fetches the familiar scope from the author's homeserver and from peers who already hold those bytes. The client serves the public familiar records it holds to a peer that asks by author key or by record URI. The user can turn serving off and keep fetching, or turn both off.

Serving a record does not endorse it, follow its author, or adopt its tag. The author stays the author. The peer is only the supplier. An indexer's score, rank, cursor, or query log is not a record and MUST NOT be fetched or served. A peer request MUST be for a key or a URI the requester names. The client MUST NOT broadcast its searches, and MUST NOT forward a peer's request to an indexer.

Tags are first-class public records in this scope. A tag shared through the mesh still names the key that wrote it and the target it points at. The recipient's index counts that tag once, under that author. Shop records and listings in the familiar scope are shared the same way. Paykit still starts only when the user buys. Locked bytes stay behind the Lock and are not served.

Budgets still apply: text before media, a cap on how many familiar keys refresh at once, and no crawl past the familiar scope unless the user widens it.

## 6. Merge

Evidence accumulates. The current view is a projection under the reader's rules.

| Question | Answered by |
|---|---|
| Are these the bytes? | A hash |
| Did this exporter ship this selection? | A set signature, or trust in the supplier |
| Did this author commit to these bytes? | An author proof, checked under its own rules |
| Did this supplier report seeing this version? | A source observation |
| Is this version current? | The reader's admitted sources, not the newest ZIP and not the export time |

An old valid signature does not freeze a record as current. Export time does not make a record newer. Two conflicting author statements both stay until an admitted successor or an explicit choice. A gap in a proof chain stays a gap. An unsupported proof stays opaque and MUST NOT show a verification badge.

The same evidence and the same policy SHOULD produce the same projection. Readers do not have to agree with each other.

## 7. Providers

Grant each role on its own: read public records, index a scope, replicate authored public data, hold an encrypted private backup, publish, resolve identity. A role MUST NOT be inferred from a README or from a different role.

A read MUST use the local index first and return those hits before any network call. If a familiar record is missing or older than the user's freshness window, the client asks peers who hold that key, then the author's homeserver. A remote indexer is for coverage outside the familiar scope, and for a familiar gap that peers and the homeserver did not fill. Indexer bytes enter the replica as the author's record. The indexer's extra fields stay labeled as that indexer's claims.

A failed public read MAY try another eligible public source. A failed private companion MUST NOT send that query to a public indexer. A catalog copy MUST NOT receive orders. Health is per role and per scope. A host can allow reads and refuse writes.

Show local retention, homeserver acceptance, and indexer visibility as separate facts. There is no single synced flag.

Changing the PKARR publishing location is an identity action. A read failover MUST NOT do it. The app MUST NOT load the identity seed to do it. Until a reviewed authorization exists for a companion, moving the public home is explicit, and the app says when it has not happened.

## 8. Commerce and disclosure

Public offers and private activity use the same folder rules and the same merge rules. Slime defines no listing schema and no marketplace enrollment. An adapter projects the shop, listing, or tag schema that is actually deployed.

| Class | Examples | Default |
|---|---|---|
| Public | Seller-selected profile, listings, public terms, selected images, tags, public bookmarks | Shared by default when the seller or the author is familiar. Also exportable when the user selects them |
| Personal | Searches, filters, private favorites, drafts, notes | Stay local. A private favorite fetches the public listing and does not itself leave the device |
| Transaction | Inquiries, quotes, orders, addresses, invoices, payment requests, tracking | Paykit, or an encrypted backup the user chose. Never a public set |

Duplicates merge on native identity and retained version. Title, image, price, and product code MUST NOT merge two sellers' stock. Copying a listing MUST NOT add quantity. An admitted withdrawal MUST NOT lose to an older catalog. Price stays in the native unit. Floating-point rounding MUST NOT authorize a total.

Local search and retained images, with the network quiet, MUST NOT open sockets. That includes analytics and remote images. Missing media stays missing until the user fetches it.

A contact link or a payment link is a hint. Starting Paykit, or opening a Lock, is a separate action against the live counterparty. An offline catalog MUST NOT reserve inventory or guarantee a price. A signature on a tag is not proof of purchase and not proof the claim is true.

## 9. What the interface shows

The user MUST be able to inspect origin, supplier, proof status, and coverage. An empty result means no match in the scope that was consulted. A signature MUST NOT be labeled as completeness, clock accuracy, current stock, or truth. An unknown global count MUST NOT be shown as zero.

## 10. Outside this specification

- A shared live view, a remote query language, a compulsory rank, or a broadcast of searches.
- An inbox for senders the recipient does not already watch.
- An automatic PKARR update from the app.
- A homeserver process inside the browser.
- A torrent client as a requirement for Exchange or Replica.
- A new encryption format. Confidential delivery uses an existing authenticated channel.
- Offline global inventory, fulfillment, or a seller reputation score.

## 11. Acceptance

Exchange is met by the import, signature, history, commerce-disclosure, and hostile-archive tests named in the [development plan](development-plan.md). Replica adds offline boot, outbox survival, familiar-scope fetch and serve, a local index that answers before any indexer, and a catalog search that makes no network requests. An inbox, and an unattended PKARR move, are not gates for either level.
