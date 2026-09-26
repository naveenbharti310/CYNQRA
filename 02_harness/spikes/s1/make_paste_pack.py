#!/usr/bin/env python3
"""Build a paste pack so S1 can be run with a chat subscription and no key.

Why this exists: a chat subscription is not an API key. You cannot point
code at it. But S1 does not measure speed or cost. S1 measures whether a
model can turn a messy objective into seven fields. A human moving text
by hand measures that just as well, as long as nobody edits the answers.

Writes PASTE_PACK.md and an empty answers folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run_s1 import load_corpus, prompt_for  # noqa: E402

RULES = """# S1 paste pack

Prompt version v2, 26 September 2026. The v1 pack of 25 August is withdrawn,
because its prompt told the model to leave fields empty while the scorer fails
empty fields. No S1 answers or scores exist in the record, so no result is
affected.

This is the version of S1 for someone with a chat subscription and no API key.
Same ten items, same scorer, same bar of 8 out of 10.

## Rules that keep the score honest

1. Start a NEW chat for every item. Ten items, ten fresh chats. If you reuse
   one chat, item 4 learns from item 3 and the score is worthless.
2. Use a temporary or incognito chat, or switch memory off first. Chat apps
   now remember earlier conversations, and a model that remembers Cynqra or the
   candidate tracker is not a clean test.
3. Paste the block exactly as written. Do not add a hint, do not rephrase the
   objective, do not tell it what you are hoping for.
4. Copy the reply back exactly. Do not fix its spelling, do not close a bracket
   it forgot, do not delete a field it left blank. A blank field is data.
5. If the reply is not JSON at all, save it anyway. That is a real failure and
   it should count as one.
6. One retry is allowed per item, and only for items that fail. The scorer
   tells you which ones. Paste the retry block in a new chat and save the second
   reply as T0X_retry.txt.
7. Write the app and model you used in answers/model.txt, one line.

## Where to save the answers

Save each reply as a plain text file in the answers folder next to this file:

    s1/answers/T01.txt
    s1/answers/T02.txt
    ...
    s1/answers/T10.txt

Or use the browser page 03_pages/cynqra-s1-paste-pack.html, which has a reply
box per item and saves one file, s1_answers.json, to put in the same folder.

## Then score it

Double click RUN_M1.bat and choose "score hand pasted S1", or run

    python s1/score_manual.py

It prints the score and writes s1_report.json marked as a manual run.

## One thing this run cannot tell you

It cannot tell you cost or speed, because you are the transport. That is fine.
S1 was never a cost test. S2 is the cost test, and S2 cannot be done this way.

"""


def main():
    corpus = load_corpus()
    (HERE / "answers").mkdir(exist_ok=True)
    (HERE / "answers" / ".keep").write_text("", encoding="utf-8")
    parts = [RULES]
    for case in corpus:
        parts.append(f"## Item {case['id']}\n")
        parts.append("Paste everything between the lines into a new chat.\n")
        parts.append("\n-----8<-----\n")
        parts.append(prompt_for(case["messy"]))
        parts.append("-----8<-----\n")
        parts.append(f"\nSave the reply as answers/{case['id']}.txt\n\n")
        parts.append(f"### Retry block for {case['id']}, only if it failed\n")
        parts.append("\n-----8<-----\n")
        parts.append(prompt_for(case["messy"], retry=True))
        parts.append("-----8<-----\n")
        parts.append(f"\nSave the retry as answers/{case['id']}_retry.txt\n\n")
    out = HERE / "PASTE_PACK.md"
    out.write_text("".join(parts), encoding="utf-8")
    print("wrote", out)
    print(f"{len(corpus)} items, {len(corpus)} new chats needed")
    print("answers folder:", HERE / "answers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
