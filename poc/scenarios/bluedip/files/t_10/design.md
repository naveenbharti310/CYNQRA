# Bluedip release 1: the owner's screen

**What:** the one screen a restaurant owner uses between services. **Why:** an owner decides an offer in a minute,
standing up, so the screen must answer "is this offer worth it?" at a glance, and that answer is the money the
restaurant keeps after food cost. **How:** three blocks on one page, in the order the owner thinks. Covers r_11.

## Screens

One page, "Today at your restaurant":

1. **The day, hour by hour:** a bar for each opening hour sized by expected covers, with the quiet hours shaded.
   Above it, the day's expected covers and revenue. While the restaurant has no history of its own, the page says
   it is showing sample data.
2. **Breakfast, lunch and dinner:** one card each, with expected covers, the quiet window and the recommended offer,
   or "no offer" when every discount would lose money, and a "Use this" button that fills in the offer builder.
3. **The offer builder:** from, until, discount and maximum customers, then "Estimate". The estimate shows, side by
   side: covers expected without the offer, customers using it, new customers it brings, customers who would have
   come anyway, revenue change, and **margin change after food cost**, highlighted green when it earns money and red
   when it loses money. Under it, the assumptions in plain words, including the food cost when it is assumed, and a
   better offer when there is one.
4. **Your offers:** a table of the offers created, each with how many customers used it out of its cap and its
   estimated margin.

## Flows

1. Morning check: the owner opens the page and reads today's quiet hours and the recommended offers.
2. Creating an offer: the owner taps "Use this" on a meal or fills in the builder, reads the margin change first,
   then the rest of the estimate, and creates the offer or takes the better one.
3. At the counter: staff mark each customer who uses the offer; the cap is never passed.
4. After the window: the owner enters the covers served, and the next estimate learns from it.
