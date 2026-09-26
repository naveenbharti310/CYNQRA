# The Cynqra Company Canon

Live export, 25 August 2026. This is the index. Read it before opening any book.

This is the single source of truth for Cynqra. If a question cannot be answered from
these five books, that is a gap in the canon. Log it in the Decision Log in Book 4 and
close the gap.

## What this is

Cynqra is written down as a canon: one doctrine plus four execution books, not one giant
document. Each book has one job, one owner, and answers one category of question.

## The five books

| Book | Answers | Owner |
| --- | --- | --- |
| Book 0: Doctrine | Why we exist and what we are | CEO (founder) |
| Book 1: Product | What we build first, precisely, and how we know it works | CPO |
| Book 2: Engineering | How we build it: decisions, schemas, contracts, security | CTO |
| Book 3: Operations | How the company runs: failures, liability, money, compliance | COO |
| Book 4: Company | Who we hire, what the next 90 days look like, and what we have decided | CEO |

## Reading order

1. Every new hire reads Book 0 first, end to end. No exceptions.
2. Then their own book: engineers read Book 2, product reads Book 1, operations reads Book 3.
3. Book 4 is shared context. It holds the team plan and the Decision Log that governs all
   the books.

For the incoming CTO that means Book 0, then Book 2, then the Decision Log in Book 4. The
rest can wait a week.

## Canon rules

- Book 0 changes rarely. It is doctrine. Changing it takes a founder decision, recorded in
  the Decision Log.
- Books 1 to 4 change constantly. Every change is versioned and dated at the bottom of the
  book.
- No orphan decisions. If a decision contradicts a book, we either update the book or
  reject the decision.
- The canon is the onboarding. If a new hire is confused after reading it, the canon is
  wrong. Fix the canon, not the hire.

## What is in this folder, and which version wins

The PDFs are the typeset books. Book 0 is at v1.0 and is current, it has not changed since
it was written. Books 1 to 4 are at v0.4.

The files ending `_LIVE.md` are exports of the working pages as they stand tonight. Where
a LIVE file disagrees with a PDF, the LIVE file wins. There are two files that matter here:

- `BOOK_4_COMPANY_LIVE.md` carries the Decision Log with all thirty decisions closed. The
  PDF version predates the G0 ratification session, so its log stops early. Use the LIVE
  file for anything about what has been decided.
- `M1_BUILD_KIT_LIVE.md` and `M1_TWO_WEEKS_LIVE.md` are the current working plan and the
  run status. They are not canon and they ratify nothing. They tell you where the work
  actually stands.

See `RECOVERY_NOTE.md` at the root of this handover for one open item about the Books 1 to
4 PDF version.
