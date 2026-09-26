# Candidate tracker: acceptance checks

1. Create: a candidate with a name is stored and starts at applied. A blank name is refused.
2. List: every candidate created is listed.
3. Stage: set_stage accepts only the closed list. An unknown stage or candidate is refused.
4. Flagged: a card in applied or screen that has not moved for seven days is flagged.
5. Stuck: a flagged card with a named reason is stuck. A reason outside the list is refused.
6. Moving on: when the stage moves past screen, the card leaves flagged and stuck at once.
7. Persistence: data survives a restart.
8. Web: /health answers, the screen loads, the API refuses bad input with an error.
9. Scope: there is no careers page, no applicant login, no email.
