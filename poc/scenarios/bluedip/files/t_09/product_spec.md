# Bluedip release 1: product specification

**What:** the owner's app, release 1. **Why:** it is the part of the business plan a restaurant pays for, so it must
show a number the owner can trust before an offer runs. **How:** one screen, described below; the acceptance checks
turn each rule into a test.

## Users

* **The restaurant owner**, on a phone or a laptop, between services (r_09, r_10, r_11).
* **Staff at the counter**, who mark each customer who uses an offer, so the cap holds.

## What the owner sees and does

1. **Today, hour by hour:** Bluedip predicts footfall and revenue, from a forecast checked against last week's numbers
   (r_06). Quiet hours are marked. As covers are served, the rest of the day is corrected.
2. **Breakfast, lunch and dinner:** expected covers and revenue for each, its quiet window, and the recommended
   offer, or "no offer" when every discount would lose money (r_10).
3. **A limited-time offer:** from, until, discount, maximum customers. Before creating it, the owner sees the
   estimate: customers using it, new customers it brings, customers who would have come anyway, revenue change and
   margin change after food cost, with the assumptions behind every estimate (r_07). A better offer is suggested
   when there is one.
4. **The offers:** each with how many customers used it out of its cap. The cap is never exceeded (r_09).
5. **Learning:** when an offer's window ends, the owner enters the covers served; Bluedip's response estimate for that
   restaurant updates.
6. **The owner's figures:** average bill and food cost. Until food cost is entered, 35% is used and shown as an
   assumption.

## Out of scope

* **No diner-facing app and no payments in the first release** (r_13). The owner tells diners about an offer their
  own way.
* No publishing of offers to dining or delivery platforms.
* One restaurant per account; chains come later.

The business plan behind this release (market analysis, financial model, compliance register, revenue management
report) is checked separately and delivered with it.
