# Covers forecast: architecture

Covers r_04 and r_07.

## Components

* forecast.py: `forecast(history, horizon)`, the Data Scientist's method, no dependencies.
* data.py: `CoversStore`, the covers history in one JSON file, validated on the way in (r_04).
* app.py and index.html: one HTTP server on 127.0.0.1 and the forecast page; `GET /api/forecast` joins the store,
  the forecast and the prep margin.
* Python 3.10 standard library only; one process on the office computer (r_07).

## Data

One JSON file named by DATA_FILE: `{"sample": bool, "days": [{"date": "YYYY-MM-DD", "covers": n}]}`. One number
per day; a later entry for a date replaces the earlier one. Writes go to a temporary file first, then replace
the old one, so a crash never leaves half a file.
