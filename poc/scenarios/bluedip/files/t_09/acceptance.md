# Bluedip release 1: acceptance checks

1. The day view lists every opening hour with expected covers and revenue, and breakfast, lunch and dinner with a
   recommendation each; sample data is said to be sample.
2. The quiet lunch window of the sample restaurant is 1 pm to 4 pm.
3. The covers served so far correct the rest of the day, within half and one and a half times the forecast.
4. An estimate shows customers using the offer, new customers, customers who would have come anyway, revenue change
   and margin change, and the assumptions behind it, including whether food cost is assumed.
5. The owner's example, 50% off for at most 15 customers from 1 pm to 4 pm, raises revenue and loses margin; the
   recommended offer adds margin.
6. No estimate and no offer exceeds its cap; the 16th customer of a 15-customer offer is refused.
7. The rule on record is enforced: no discount above 50%, none below food cost, no window outside opening hours.
8. A finished offer updates the response estimate.
9. Data survives a restart. /health answers, the page loads, and there is no payment or diner route.
