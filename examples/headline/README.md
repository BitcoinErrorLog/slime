# Headline fixtures

The files for the Alice, Bob, Carol, and Dana acceptance test. Dana is the seller from `shops-public/`. `test_headline.py` runs the test's data path offline against these files.

| Path | What it holds |
|---|---|
| `bob-provider/` | Bob's signed provider advertisement |
| `bob-index-1/` | Bob's first shared index, covering Dana's key |
| `bob-index-2/` | The next snapshot, with Carol's tag |
| `bob-answers/` | Two query responses from Bob's endpoint |
| `carol-notice/` | Carol's notice and the tag it points to |
| `alice-route/` | Alice's signed route, her home statement, and two statements to reject |
| `delegations.json` | The UKD delegations the checker is given |

`delegations.json` is the checker's input, not a Slime format. It holds, for Alice and Bob, the `app_keys` entries of their `slime` KeyBinding as the UKD library returns them after verifying the KeyBinding and each AppCert against the identity key. The KeyBinding and AppCert wire formats belong to UKD.
