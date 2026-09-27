# Book 4 Decision Log: proposed additions, 26 September 2026

Prepared by the acting officers. Nothing here is binding until the founder marks it in
the Book 4 Decision Log (the Notion page that BOOK_4_COMPANY_LIVE.md exports). The export
is left untouched so it keeps matching the page it came from.

Mark each row: ratified, amended, rejected, kept open or deferred.

## Rows to vote

| ID | Decision proposed | Owner | Why now |
| --- | --- | --- | --- |
| D-31 | The Objective System proposes a complete structured objective, marks every field it inferred rather than read, and the founder confirms. It never adds features, users or constraints the founder did not state or imply. | CPO | Product basis for S1 prompt v2. Book 1 P0 #2 and section 9 already imply it; no row says it. Must be ratified before S1 runs, because S1 prompt v2 depends on it. |
| D-32 | Amend the D-18 event contract: add protocol_hash and test_ids to the envelope (break b_009), and add run.started, run.closed, protocol.sent, task.paused, verification.started and export.completed to the catalog. | CTO | The kit already writes these. The ratified catalog does not contain them. Canon CI finding 7. |
| D-33 | M1 is unblocked by the founder, not by the hire: the founder runs S1 and S2 with a spend capped API key, by double clicking RUN_M1.bat or by handing the key to Claude for one session and revoking it after. The CTO search continues as hire number one, because M2 cannot be built without an engineer. | CEO | M1 was due to close on 8 September. It has waited 18 days on a hire. The spikes cost under ten dollars. |
| D-34 | Recover the v1.2 build (Books 1 to 4 at v0.5) and G0_Ratification_Packet_v1.2.pdf. If either cannot be found, rewrite the missing text for D-19, D-23, D-24, D-25, D-26, D-27 and D-28 and ratify it again. | CEO | Those rows cite Book 2 sections 8 and 9, Book 3 section 9 and Book 4 sections 7 and 9. None of those exist in the v0.4 PDFs in the handover. The ratified rows point at text the team cannot read. |

## Recorded by the acting CTO, founder may reverse

| ID | Decision | Owner |
| --- | --- | --- |
| D-35 | S3 v1 (9 of 10) is restated and does not count as evidence for G2. The record is kept. S3 v2, with seeds and controls written blind and both tiers running, is required before G2 can pass. See 02_harness/spikes/s3/S3_V1_RESTATEMENT.md. | CTO |

## Recorded on the founder's instruction, 26 September 2026

| ID | Decision | Owner |
| --- | --- | --- |
| D-36 | Build an end to end POC now, with screen mockups, tested code and a demo video, ahead of the M2 gate. This overrides "no dashboards or design before M2" for the POC only. The POC is a demonstration and is never quoted as evidence for S1, S2, S3 or any gate. Spec: poc/POC_SPEC.md, which carries working text for D-27 and D-28 until D-34 restores the originals. Status 26 Sep: built, 95 of 95 tests pass, results in poc/TEST_REPORT.md. | CEO |

## Needs one line from the founder

The G0 session record, 01_history/g0_results.json and the g0-results page, says D-22 was
"kept open, not voted" and D-7, D-8 and D-9 were "left alone". The live Decision Log says
all four are Decided, with Hybrid chosen for D-22. Both cannot be the record. If the
founder decided after the session, add a dated line saying so, and the session record is
then superseded, not edited.

## Canon CI, first run, 26 September 2026

D-26 made a weekly consistency review a standing control. It had never run. Findings:

1. D-19 (Workstream and Run), D-23, D-24, D-25, D-26, D-27, D-28 cite sections missing from
   the v0.4 books. Workstream and Run exist only as field lists in
   02_harness/kit/schema/entities.json. D-27 and D-28 exist only as one line summaries in
   the G0 session page.
2. RECOVERY_NOTE.md says v0.4 and v0.5 differ only in wording. Finding 1 shows sections were
   added, so that claim is wrong.
3. D-8 in the live log cites a "Book 3 three quote median". Book 3 v0.4 has no such method.
4. RUN.md, run_report.md, the run 002 board and the close page still show 3 founder
   interventions and 4.0 objects per task. The audit corrected these to 2 and 3.0. measures.json is right.
5. 01_history/S3_MEMO.md (run 002, catch 0.4) and 02_harness/spikes/S3_MEMO.md (S3 v1,
   9 of 10) share a name and report different things.
6. 03_pages/README.md says the G0 results page shows Hybrid for D-22. The page says kept open.
7. The kit's event types and envelope columns go beyond the ratified D-18 catalog. D-32
   proposes the fix.
8. Run 002 event times are generated in 37 second steps from 20:05, not read from a clock,
   and decision_001's approval is logged on 25 August with the founder as actor although the
   founder acted on 24 August. Replay and audit must not read those times as real.
9. STATE_OF_PLAY.md and RECOVERY_NOTE.md point at 01_history/run_002/ and 01_history/g0/.
   01_history has no subfolders.
10. 02_harness/event_log.csv is the void run 001 log. 01_history/event_log.csv is run 002.
    Same name, different runs.
