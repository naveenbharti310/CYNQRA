# Covers forecast: method

Covers r_03.

## Method

Covers follow the week: Fridays and Saturdays are busy, Mondays quiet. Each day ahead is forecast as the average
of the same weekday over the last four weeks. The average keeps the weekly pattern and smooths one-off nights; four
weeks follows a trend without chasing noise. Standard library only: `forecast(history, horizon)` in forecast.py.

## Evaluation

The platform backtests the forecast on the last 14 days of a history it holds back, against the baseline of the
same weekday a week before (last week's numbers). The forecast is accepted only if its mean absolute error is no
worse than the baseline's. Its tests check the shape of the answer: one non-negative number per day ahead.
