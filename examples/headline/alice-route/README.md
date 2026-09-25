# Alice's route and home statement

`route.json` lists the homeservers Alice enrolled, in her order, her failover key, and her notice provider. Her identity key signs it, through Ring. `home.json` is what her failover key signs after her primary homeserver refused her writes: it names the enrolled alternate. The failover key is an AppKey Alice's identity delegates through UKD, and `cert_id` names its AppCert. Both files sit on every enrolled homeserver.

`rejected/` holds two home statements a reader must ignore: one names a homeserver the route does not enroll, and one is signed by a key that is not the route's failover key.

- Identity key: `zefk98sfbnhn8gtkwgid6sw4qkph3hf8omghoe3yp9g7jpm84t1y`
- Failover key: `wakh6f8m5fty5jgw3koycda7tqdikdck8bxcg6gfkqdwte4kpqpo`
- Primary homeserver key: `kh3znzd47hhhg4njygjrhb1ppduyepdq39qons4a59cxqa5jny5o`
- Alternate homeserver key: `p86g5f5mywsn3ccsrcxynhr89g1xd8n3jthafehuucf4rr1qgd8y`
