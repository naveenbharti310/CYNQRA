# Bluedip's models: method

The Data Scientist's method (r_06, r_07). **What:** how Bluedip predicts footfall and revenue, and estimates an
offer. **Why:** every number the owner sees comes from these models, so each must be simple enough to explain and
checked on data it has not seen. **How:** four steps, each below, with how it is evaluated.

## Method

1. **Covers a day.** Each day ahead is the average of the same weekday over the last four weeks. Covers follow the
   week; the average keeps that pattern and smooths one-off nights. `forecast(history, horizon)` in forecast.py.
2. **Covers by hour and by meal.** The day's covers are spread over the opening hours by the restaurant's hourly
   pattern; revenue is covers times the average bill. An hour is quiet when it expects under 60% of its meal's
   busiest hour.
3. **During the day.** The covers already served replace the forecast for past hours, and correct the hours still
   to come by the same ratio, kept between half and one and a half times, so one odd hour cannot swing the day.
4. **An offer.** In its window, *expected* covers come anyway. The offer brings new customers in proportion to the
   discount (the **response**), and some of the customers who come anyway use it (the **take-up**). The cap limits
   both. Revenue change = new customers × bill × (1 − discount) − customers who would have come anyway × bill ×
   discount. Margin change is the same after food cost. The recommendation is the discount, within the rule on
   record, that adds the most margin; none when every discount loses money.
5. **Learning.** Each finished offer shows its real response: the covers above those expected, per unit of discount.
   The estimate is the starting assumption (response 1.2, take-up 0.3), weighed as three offers, averaged with what
   the restaurant's own finished offers showed.

## Evaluation

* **Covers a day:** the platform backtests the forecast on 14 days it has not seen, against last week's numbers. It
  is accepted only if its average error is no larger.
* **Offers:** every finished offer compares the customers estimated with those who came; the screen shows how many
  offers the response rests on. Until a restaurant has finished about five, the estimate is mostly the starting
  assumption, and it says so.
* **Not yet evaluated:** the hourly pattern comes from sample data until the pilot restaurants' own hourly covers
  arrive; it is re-estimated from them in the pilot.
