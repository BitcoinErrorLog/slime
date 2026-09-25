# Alice's route and failover

`route.json` lists the homeservers Alice enrolled through Ring, in order of preference, her failover key, and her notice providers. `identity.txt` is the `_slime` TXT value in the PKARR packet of Alice's identity key: it pins the route by hash. `failover.txt` is the `_slime` TXT value in the PKARR packet of Alice's failover key after her primary homeserver refused her writes: it names the enrolled alternate.

- Identity key: `4pp1y4xkdpzquyp9wt7kxs395ihj93ioijt5nxq7xbr7khod4hcy`
- Failover key: `y8s7w4d9d7fzih797b88ymx9qobggzczc9rc3ebdyhcfhsazko1y`
- Primary homeserver key: `pfju6i9x3ybssnjs6ibsy71tsznpwga7uh9ee6wzy5rfsnsh18oy`
- Alternate homeserver key: `q137yp465ytbgfj85k5gas64o99kaii5dwzgay8uogcfgt3bqiwo`
