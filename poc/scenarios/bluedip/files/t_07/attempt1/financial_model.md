# Financial model: Bluedip

The CFO's model (r_03). **What:** how Bluedip makes money, what it costs, and how much funding it needs. **Why:** the
founder needs to know the price owners will accept and how long the money lasts. **How to read it:** every figure is
an **assumption** until the pilot measures it; the last section says which ones matter most. Amounts in rupees;
1 lakh = 100,000.

## Costs

* **Per restaurant, per month:** servers ₹150, support ₹100.
* **Team and running costs:** ₹5.8 lakh a month (four people at ₹1.2 lakh on average, plus ₹1 lakh other).
* **Winning a restaurant:** ₹6,000 (visits, onboarding, the free trial).

## Pricing

**₹1,999 a month per restaurant**, after a 30-day free trial. Why a restaurant pays it: in the Data Scientist's
example, Bluedip's recommended lunch offer adds about ₹340 of margin in one quiet window. Two quiet windows a day,
26 days a month, is about ₹17,800 a month, nine times the price (assumption: the pilot measures it). No commission on
offers, so an owner keeps every rupee an offer earns.

## Revenue

Margin per restaurant after servers and support: **₹1,749 a month (87%).**

| Month | Paying restaurants | Cash in the month | Cash so far |
| --- | --- | --- | --- |
| 4 (paid launch; 12 pilots convert) | 52 | −₹7.3 lakh | −₹25.9 lakh |
| 9 | 227 | −₹4.2 lakh | −₹53.0 lakh |
| 12 | 316 | −₹2.7 lakh | −₹62.5 lakh |
| 18 | 464 | −₹0.1 lakh | **−₹69.2 lakh (the low point)** |
| 19 | 486 | **+₹0.3 lakh (break-even)** | −₹68.9 lakh |
| 24 | 581 | +₹2.0 lakh | −₹62.3 lakh |

A restaurant pays back what it cost to win in 3.4 months; at 4% monthly churn it is worth about ₹50,000 over its
life, eight times what it cost.

## Funding

**Raise ₹85 lakh:** the ₹69 lakh low point in month 18, plus about 20% for delays. The pilot (months 1 to 3) costs
₹18.6 lakh and is the first milestone for investors: twenty restaurants' own results.

## Assumptions

The ones that move the answer most:

1. **New restaurants a month.** At 25 instead of 40, break-even moves from month 19 to month 30 and the low point
   deepens to ₹92.5 lakh.
2. **Price.** At ₹1,499, break-even moves to month 29 and the low point to ₹1.01 crore.
3. **Churn.** At 6% a month instead of 4%, break-even moves to month 23 and the low point to ₹76.9 lakh.
4. **The margin Bluedip adds.** If the pilot shows owners gaining less than the price, nothing else here holds.

Confirm with a chartered accountant: tax, GST on subscriptions, and the company structure for raising funds.

## The numbers the platform recomputes

Every figure above that follows from these inputs is recomputed by the platform; each input says where it comes from.

```json
{"currency": "INR",
 "inputs": {
  "price_per_month": {"value": 1999, "basis": "assumption"},
  "cost_to_serve_per_month": {"value": 250, "basis": "assumption"},
  "fixed_costs_per_month": {"value": 580000, "basis": "assumption"},
  "cost_to_win": {"value": 6000, "basis": "assumption"},
  "monthly_churn": {"value": 0.04, "basis": "assumption"},
  "customers_per_month": {"value": 40, "basis": "assumption"},
  "months_before_revenue": {"value": 3, "basis": "assumption"},
  "funding": {"value": 8500000, "basis": "assumption"}},
 "claims": {"margin_per_customer": 1749, "payback_months": 3.4, "lifetime_value": 49975,
            "break_even_month": 19, "funding_needed": 6920000, "reaches_profit_before_money_runs_out": true}}
```
