# S1 paste pack

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

## Item T01
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
I need a simple tool for my cafe so waiters take orders on a tablet and the kitchen sees them. Stop losing paper tickets. Keep it cheap.
-----8<-----

Save the reply as answers/T01.txt

### Retry block for T01, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
I need a simple tool for my cafe so waiters take orders on a tablet and the kitchen sees them. Stop losing paper tickets. Keep it cheap.
-----8<-----

Save the retry as answers/T01_retry.txt

## Item T02
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Build me an internal tracker so my two recruiters can log candidates, set a stage, and I can see who is stuck. No public careers site.
-----8<-----

Save the reply as answers/T02.txt

### Retry block for T02, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Build me an internal tracker so my two recruiters can log candidates, set a stage, and I can see who is stuck. No public careers site.
-----8<-----

Save the retry as answers/T02_retry.txt

## Item T03
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
We run a small clinic. Reception keeps a shared spreadsheet of appointments and it breaks every week. I want staff to book, move, and cancel slots. Patients should not see the admin screen.
-----8<-----

Save the reply as answers/T03.txt

### Retry block for T03, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
We run a small clinic. Reception keeps a shared spreadsheet of appointments and it breaks every week. I want staff to book, move, and cancel slots. Patients should not see the admin screen.
-----8<-----

Save the retry as answers/T03_retry.txt

## Item T04
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Inventory for a tiny warehouse. Scan boxes in, scan boxes out, show what is low. Do not connect to accounting yet.
-----8<-----

Save the reply as answers/T04.txt

### Retry block for T04, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Inventory for a tiny warehouse. Scan boxes in, scan boxes out, show what is low. Do not connect to accounting yet.
-----8<-----

Save the retry as answers/T04_retry.txt

## Item T05
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
A donor CRM for our nonprofit. Store name and gift date only. I need a list and a way to add a gift. No email blasts.
-----8<-----

Save the reply as answers/T05.txt

### Retry block for T05, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
A donor CRM for our nonprofit. Store name and gift date only. I need a list and a way to add a gift. No email blasts.
-----8<-----

Save the retry as answers/T05_retry.txt

## Item T06
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Help desk for my 8 person SaaS. Customers open a ticket, we set status, they see status. No chat. Email is enough later.
-----8<-----

Save the reply as answers/T06.txt

### Retry block for T06, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Help desk for my 8 person SaaS. Customers open a ticket, we set status, they see status. No chat. Email is enough later.
-----8<-----

Save the retry as answers/T06_retry.txt

## Item T07
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Course waitlist. People join a list, I approve them into a cohort, they get a seat. Payments stay off this system.
-----8<-----

Save the reply as answers/T07.txt

### Retry block for T07, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Course waitlist. People join a list, I approve them into a cohort, they get a seat. Payments stay off this system.
-----8<-----

Save the retry as answers/T07_retry.txt

## Item T08
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
I manage 12 rental units. I need tenants, leases, and a repair ticket per unit. Tenants should not edit leases.
-----8<-----

Save the reply as answers/T08.txt

### Retry block for T08, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
I manage 12 rental units. I need tenants, leases, and a repair ticket per unit. Tenants should not edit leases.
-----8<-----

Save the retry as answers/T08_retry.txt

## Item T09
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Make a board for my hardware shop jobs. Job comes in, parts reserved, job done. One shop, one owner, no multi location.
-----8<-----

Save the reply as answers/T09.txt

### Retry block for T09, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
Make a board for my hardware shop jobs. Job comes in, parts reserved, job done. One shop, one owner, no multi location.
-----8<-----

Save the retry as answers/T09_retry.txt

## Item T10
Paste everything between the lines into a new chat.

-----8<-----
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
We need a CRUD app for grant applications. Applicant submits, reviewer scores, I decide. Keep files in our drive, do not store passports.
-----8<-----

Save the reply as answers/T10.txt

### Retry block for T10, only if it failed

-----8<-----

Retry. Fill every field the text states or clearly implies, and list the keys you inferred in inferred_fields. Do not add facts the founder did not state or imply.
Convert the founder objective into the Cynqra structured objective.
The founder will review and confirm your answer, so fill every field.
Where the text states a field, use its words.
Where the text only implies a field, write the most reasonable reading and
list that key in inferred_fields.
Do not add features, users, or constraints the founder did not state or
clearly imply.
Leave a field empty only if nothing in the text supports any reading, and
list that key in missing_fields.

Return JSON only with these keys:
product
target_customer
primary_outcome
business_outcome
success_criteria
constraints
priorities
inferred_fields
missing_fields

Founder objective:
We need a CRUD app for grant applications. Applicant submits, reviewer scores, I decide. Keep files in our drive, do not store passports.
-----8<-----

Save the retry as answers/T10_retry.txt

