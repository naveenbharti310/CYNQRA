S1 MEMO: Objective structuring
Date: 27 September 2026
Spike: S1
Result: BAR MISSED. 5 of 10 on both local models. The bar is 8 of 10.

Question
Can a model turn a founder's messy sentence into Cynqra's seven-field structured
objective well enough that the founder only confirms it?

Bar (set 24 August, unchanged)
8 of 10 items pass. An item passes when all seven fields are filled and at least four
of them cover half the words of the expected answer. One retry per failed item.
Corpus, scorer and bar unchanged; prompt v2 of 26 September (see s1/RULINGS.md R2).

How it was run
GitHub Actions run 36299849447, commit 34500e3, 27 September 2026.
spikes/run_local.py started the desktop app's own llama-server (llama.cpp b11201) and ran
s1/run_s1.py against it. Temperature 0, seed 42.
Machine: GitHub-hosted Linux runner, 4 CPU threads (AMD EPYC), 15.6 GB RAM, no GPU.
This is a laptop-class CPU, not the API model the corpus was written against.

Score
model                          passed  calls  tokens in  tokens out
Qwen3.6 35B-A3B, 2-bit (Q2)    5 / 10     16      3,274       2,668
gpt-oss 20B (reasoning low)    5 / 10     17      4,287       4,980
No model call failed on either run (errors: none), so both are scored results, not unrun.

Per item (attempts in brackets, then strong fields out of 7)
item   Qwen3.6 35B-A3B Q2      gpt-oss 20B
T01    fail (2)  0             pass (1)  4
T02    pass (1)  4             pass (1)  4
T03    pass (2)  5             pass (2)  5
T04    pass (1)  4             fail (2)  3
T05    fail (2)  2             fail (2)  2
T06    fail (2)  3             pass (1)  4
T07    pass (1)  5             fail (2)  1
T08    fail (2)  3             fail (2)  3
T09    fail (2)  4, a field empty  pass (2)  4
T10    pass (1)  4             fail (2)  3

What fails
- The weakest fields are the same on both models: business_outcome in 17 of 20 answers,
  then success_criteria. The models fill them, but not with the founder's words.
- Only T05 and T08 failed on both. The other misses differ by model, so neither model
  is simply worse; each is 5 of 10 on a different five.
- 5 of the 10 failing answers left a field empty (T09 on Qwen had 4 strong fields and
  still failed on the empty one). 3 filled all seven and missed by one field (3 strong
  where 4 are needed).

What this proves
- On a 4-thread laptop CPU, neither open model Cynqra ships by default structures a
  founder objective well enough to skip the founder's edit. The product's own flow
  already has the founder confirm and correct the objective (Book 1 P0-2), so this
  failure costs an edit per objective, not a broken journey.
- The run is real: every answer came from the model, the scorer is the one of 24 August.

What it does not prove
- It says nothing about a hosted frontier model; the corpus was written expecting one.
  S1 on Qwen3.5-35B-A3B, GLM-4.7 and Kimi K2.5 is ready to run on the [hf] route once
  the HF_TOKEN repository secret exists.
- The Q2 quantisation of Qwen3.6 costs quality; a Q4 run needs more than 16 GB.
- Ten items is a small sample: one item is ten points.

Decision owner
Whether this blocks Book 4 is the founder's call. Recommendation: do not treat S1 as
passed. Run the hosted route before deciding; until then the founder-confirm step stays
mandatory, which it already is.
