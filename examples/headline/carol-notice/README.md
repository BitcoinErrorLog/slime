# Carol's notice

`notice.json` is what Carol's client posts to a provider that covers Dana's key after tagging Dana's image post. It carries proof of work at Bob's published floor of 8 bits, bound to the target, the source, and the hour. The record under `records/` is the tag as Carol's homeserver serves it. The provider and the recipient both fetch the source and check that it references the target.
