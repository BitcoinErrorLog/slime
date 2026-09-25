# Alice's services and home statement

`services.json` lists Alice's notice provider. Her app publishes it through its own homeserver session. `home.json` is what her designated publisher signs after her primary homeserver refused her writes. It names her alternate, and it carries the Pubky grant whose client key signed it, with write on `/pub/`. A reader accepts `home` only if it is one of the `_pubky` records in Alice's PKARR packet. The tests pass those targets as the PKARR library would resolve them: primary, then alternate.

`rejected/` holds three statements a reader must ignore: one names a homeserver outside her `_pubky` records, one is signed by a key that is not the grant's client key, and one carries a grant that can only read `/pub/slime/`.

- Identity key: `cxhu1uo1w81etszkisa3fnrr18yokw4rffighbrk3d13xpkexfay`
- Publisher key: `nea4aju311rizw356nmgxf5n6xm65euoju6oi65zjff85tcyoj9o`
- Primary homeserver key: `8dffkmdfafteuceeexmkqo8e1otqqf8d456dbbwf1x7ic9sgafry`
- Alternate homeserver key: `rgfjuapu5x6uw1t6n6ikq38t7p8hrbqhjgy9u7u7od1k4dts7egy`
