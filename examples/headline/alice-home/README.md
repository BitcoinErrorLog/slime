# Alice's services and home statement

`services.json` names Alice's mirror, which republishes her PKARR packet and carries her home statement. `home.json` is what her failover key signs after her primary homeserver refused her writes while still serving stale reads. It names her alternate as the homeserver that decides her edits, and it carries the Pubky grant whose client key signed it. A reader accepts `home` only if it is one of the `_pubky` records in Alice's PKARR packet. The tests pass those targets as the PKARR library would resolve them: primary, then alternate.

`rejected/` holds three statements a reader must ignore: one names a homeserver outside her `_pubky` records, one is signed by a key that is not the grant's client key, and one carries a grant that can only read `/pub/slime/`.
