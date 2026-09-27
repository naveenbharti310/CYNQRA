D-22 COUNSEL REFERRAL
Status: draft for founder to send. Not sent. Not voted.
Owner: CEO, COO, and counsel
Date prepared: 25 August 2026

Question
When a customer asks for deletion, what happens to the immutable event history?

Design rule already in force (not a counsel decision)
Event payloads carry no personal data. Each company's data sits under its own keys.
G0 does not vote D-22. G0 only records that this referral was sent.

Options to review
1. Key destruction. Events remain. The company's encryption keys are destroyed,
   so its history becomes unreadable. Cheapest. Confirm whether this satisfies
   erasure duties in the jurisdictions we will sell into first.
2. Personal data outside events. Events carry references only. Personal data
   lives in erasable stores. More engineering. Strongest erasure story.
3. Hybrid. Options 1 and 2 together. Recommended to counsel. Fall back to 1
   if cost dominates.

What we need back
- Which option is lawful for erasure requests in our first markets.
- Whether option 1 alone is enough, or only as a fallback.
- Any wording that must appear in customer terms.
- Whether a retention window is required before key destruction.

Do not treat silence as ratification.
