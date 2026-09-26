REPLAY t_002 FROM THE EVENT LOG ONLY

Events that mention t_002: 5

What the log is enough for
Owner w_eng_b. LOW risk. Started after a Handoff from Engineer A.
A Blocker went to PM. A second Handoff followed. Then write_files, then VERIFIED.

What the log is not enough for
- Closed list of stages. protocol.sent payloads name the file, not allowed_stages.
- Blocker description. Only the filename blocker.json is in the event payload.
- Test names and pass counts. verification.completed has a verdict, not the suite.
- store.py source. The log records write_files, not the bytes.

Requirement: event payloads must carry the protocol object hash and the closed lists they name, or replay is a skeleton.
