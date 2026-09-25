# Alice's services and home statement

`services.json` lists Alice's notice provider. Her app publishes it through its own homeserver session. `home.json` is what her designated publisher signs after her primary homeserver refused her writes. It names her alternate, and it carries the Pubky grant whose client key signed it, with write on `/pub/`. A reader accepts `home` only if it is one of the `_pubky` records in Alice's PKARR packet. The tests pass those targets as the PKARR library would resolve them: primary, then alternate.

`rejected/` holds three statements a reader must ignore: one names a homeserver outside her `_pubky` records, one is signed by a key that is not the grant's client key, and one carries a grant that can only read `/pub/slime.pubky.app/`.

- Identity key: `erq43o3ogwsoa9g7jdgppewxhauk9rba6rkptsocdzus65ysouqo`
- Publisher key: `t6qmc8ni3y3eangwa3zzewut7ntqaewqx3b14pq8iqparwqk78py`
- Primary homeserver key: `whuzjiat7b561ocd3akkd36scbzdoc5y9m8oieyjjpjx6sz1hpno`
- Alternate homeserver key: `68zirzf5ehoxg1bbkxt31x3nmdx76ows713hewumwm6kce4hwp1o`
