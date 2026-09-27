# Covers forecast: acceptance checks

Covers r_01, r_02, r_05 and r_08.

1. Horizon: the forecast covers exactly the 14 days after the last recorded day.
2. Prep plan: each day's prep is the forecast plus the margin the founder decides, rounded up to whole covers.
3. Weekly pattern: a history that repeats every week is forecast as the same week again.
4. Weekends: Saturdays and Sundays are marked on the page.
5. History: a day's covers can be recorded; a bad date or a negative or fractional count is refused.
6. Accuracy: the forecast's mean absolute error on held-out days is no worse than last week's numbers.
