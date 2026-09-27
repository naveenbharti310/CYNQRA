# Covers forecast: product specification

Covers r_01, r_02, r_05 and r_08.

## Users

The head chef and the floor manager of one restaurant (r_01). They check the page each morning to plan prep and
staff. Nobody outside the restaurant uses it.

## What it does

* Keeps the daily covers history the restaurant already records, one number a day, and takes new days as they
  come (r_02).
* Forecasts expected covers for each of the next 14 days from that history. The forecast must beat last week's
  numbers (the same weekday a week before) on held-out days.
* Shows each day's forecast and prep plan on one page, weekends marked (r_05).
* Acceptance checks are automated and run on every change (r_08).

## Out of scope

No customer personal data, no bookings, no accounts: a date and a count of covers only. No cloud service: it
runs on the office computer. No ordering or supplier integration in this release.
