HOW TO RUN THE SPIKES
Rewritten 26 September 2026. The 25 August version pointed at /data paths from
the old sandbox and at an S2 runner that was not in the handover.

On Windows, no typing
Double click RUN_M1.bat in the handover root. It finds Python, asks for the
API key in a hidden prompt, and runs the spike you choose. The key is never
written anywhere. If Python is missing it opens the download page.

On any machine
From the 02_harness folder, with one of these set:

  ANTHROPIC_API_KEY   default model claude-sonnet-5
  OPENAI_API_KEY      default model gpt-4o-mini
  CYNQRA_MODEL        optional, any current model id

  python spikes/preflight.py        where things stand
  python spikes/s1/run_s1.py        S1, 10 items, bar 8 of 10
  python spikes/s2/run_s2.py        S2, 12 tasks, bar in s2/RULINGS.md
  python spikes/s3v2/run_s3_v2.py   S3 v2, only after blind seeds are sealed
  python spikes/test_spikes.py      harness tests, no key needed
  python kit/test_kit.py            verifier kit tests, no key needed

Exit codes
0 met the bar. 1 scored and missed the bar. 2 refused, nothing to score with.
3 a model call failed, nothing scored, the spike is unrun. 4 wiring test only.

Rules that keep the result honest
1. Do not edit s3/seeds.json, S2_ESTIMATE.md, s2/tasks.json, s1/corpus.json or
   any RULINGS.md after scoring starts.
2. A token count estimated from a shell command is not a measured S2 result.
   run_s2.py writes those runs to s2_wiring_test.json only.
3. A run with no model, or a model that errors, is not a failed spike. It is
   an unrun spike.
4. stub_model.py is a wiring aid, not a model. It refuses S1 prompts.
5. Every scored run exports a zip the same day. RUN_M1.bat does it for you,
   into the exports folder.
6. M2 does not start until S1 and S2 have real scores and someone writes the
   go or no go in Book 4.
