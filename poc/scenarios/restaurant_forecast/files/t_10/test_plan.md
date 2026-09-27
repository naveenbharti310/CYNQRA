# Covers forecast: test plan

Covers r_08.

## Strategy

* Unit tests beside each module: the forecast's shape, the store's validation, the app's routes.
* Acceptance tests (test_acceptance.py) check the numbered acceptance checks against the product's own functions.
* The platform backtest checks accuracy; the deploy step's smoke checks run against the preview and the live URL.
* Every test in the repository reruns on every change.

## Acceptance

Acceptance checks 1 to 4 are automated in test_acceptance.py; check 5 is covered by test_data.py and test_app.py;
check 6 is the platform backtest, which no test of ours can replace.
