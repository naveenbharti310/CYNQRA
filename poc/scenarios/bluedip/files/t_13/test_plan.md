# Bluedip release 1: test plan

**What:** how every promise of release 1 is checked before it counts. **Why:** an owner acts on Bluedip's numbers,
so a wrong estimate costs a restaurant real money. **How:** three layers of tests, run again on every change.
Covers r_14.

## Strategy

* Unit tests beside each module: the forecast (test_forecast.py), the demand and offer engine (test_offers.py) and
  the app's routes (test_app.py).
* Acceptance tests (test_acceptance.py) check the numbered acceptance checks against the running app, the way an
  owner uses it.
* The platform's backtest checks the forecast against last week's numbers on days it has not seen; the release's
  smoke checks run against the preview and the live address.
* Every test in the repository runs again on every change.

## Acceptance

Acceptance checks 1 to 9 are each a test in test_acceptance.py. Check 3's accuracy and the forecast's accuracy are
also covered by the platform's backtest, which no test of ours replaces.
