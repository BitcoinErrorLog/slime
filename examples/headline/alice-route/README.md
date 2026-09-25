# Alice's route and home statement

`route.json` lists the homeservers Alice enrolled, in her order, her failover key, and her notice provider. Her identity key signs it, through Ring. `home.json` is what her failover key signs after her primary homeserver refused her writes: it names the enrolled alternate. The failover key is an AppKey Alice's identity delegates through UKD, and `cert_id` names its AppCert. Both files sit on every enrolled homeserver.

`rejected/` holds two home statements a reader must ignore: one names a homeserver the route does not enroll, and one is signed by a key that is not the route's failover key.

- Identity key: `t6k4qwfko1a4h7yk78kgyhzzzx6pgdfk4sz69c96znto6agyupxo`
- Failover key: `3dh8ry34s13z8xfspam6pk7g9uejjm64uu943yenu697h7cfchao`
- Primary homeserver key: `nrjsadykf1wbhyfwotdci9s1nopnbiseqe7xcbwf8nufq6bbejyo`
- Alternate homeserver key: `an1677yn1o5xw5uewooihkm6ar74jr1qwbfxqh7nag8mi31e9yyy`
