# S1 rulings

Recorded 26 September 2026, before any S1 answer or score exists in the record.
Acting CTO (spike owner) with the acting CPO on R2, because R2 is a product call.
Rule one of this project says a bar is set before the test and never moves. These
rulings change how the test is carried, not what passes it.

## Unchanged

1. corpus.json: the ten messy objectives and the expected answers of 24 August.
2. The scorer in run_s1.py: all seven fields filled, and at least four of them
   covering half the words of the expected answer.
3. The bar: 8 of 10, one retry per item.

## R1. A failed model call is an unrun spike, not a failed one

Found: model_adapter caught every provider error and handed back empty text. run_s1.py
scored the empty text and wrote "passed 0, this is the S1 result". Reproduced on
26 September with a failing command and with an invalid key. It would also have fired
on the first real attempt with an Anthropic key, because the default model id,
claude-sonnet-4-20250514, was retired by Anthropic on 15 June 2026.

Ruling: the first model error stops the run, writes s1_unrun.json, exits 3, and never
writes s1_report.json. The Anthropic default is now claude-sonnet-5. A shell command
that exits non zero is an error, not a reply.

## R2. The prompt asks for what the product needs

Found: prompt v1 said "Invent no fields. If a field is not in the text, leave it
empty." The scorer fails any empty field. None of the ten objectives states a
priority, so a model that obeyed v1 fails every item. Reproduced on 26 September: a
simulated model that returns every expected answer word for word but leaves priorities
blank scores 0 of 10. The same answers with priorities filled score 10 of 10.

Product basis: Book 1 P0 requirement 2 converts free text into a structured objective
that the founder confirms, and Book 1 section 9 has the founder see a full structured
objective in the first sitting. The Objective System is meant to propose a complete
reading and let the founder correct it. It is not meant to return blanks.

Ruling: prompt v2 asks the model to fill every field, use the founder's words where
they exist, write the most reasonable reading where a field is only implied, list those
keys in inferred_fields, and never add features, users or constraints the founder did
not state or imply. v1 is kept as prompt_v1_24aug.txt. The retry text says the same.

What v2 does not do: it carries no examples and no hints drawn from the expected
answers. The author of v2 had read corpus.json, which is why v2 is generic and changes
the instruction only.

## R3. Hand carried runs must use a clean chat

Chat apps now keep memory across conversations. A model that remembers Cynqra or the
candidate tracker is not a clean test, and item T02 is the candidate tracker itself.
Rule added to the paste pack: temporary or incognito chat, or memory switched off, and
the app and model are written down in answers/model.txt.
