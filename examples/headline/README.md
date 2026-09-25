# Headline fixtures

The files for the Alice, Bob, Carol, and Dana acceptance test. Dana's records are the pubky.app records from `shops-public/`. `test_headline.py` runs the test's data path offline against these files.

| Path | What it holds |
|---|---|
| `bob-provider/` | Bob's signed provider advertisement |
| `bob-slice-1/` | Bob's first slice, covering Dana's key |
| `bob-slice-2/` | The next snapshot, with Carol's tag |
| `bob-answers/` | Two query responses from Bob's endpoint |
| `carol-notice/` | Carol's notice, with proof of work, and the tag it points to |
| `alice-home/` | Alice's services document, her home statement, and three statements to reject |

Provider and publisher keys are client keys of Pubky grants, encoded as pubky-common encodes them. Signatures are detached JWS.
