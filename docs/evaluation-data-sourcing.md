# Evaluation data sourcing

## Current local evidence

The local provider archive contains repeated Upstox `TCS.NS` daily-price
snapshots. One archived snapshot records a close of INR 2,105.00 for
2026-09-18, with instrument key `NSE_EQ|INE467B01029`. These archives are
usable for replay and deterministic indicator checks, but they do not include
an independent provider's matching TCS observation.

## Independent-source policy

Use an independently retrieved, timestamp-compatible source only when its
terms permit the intended local evaluation storage. Store the exact response,
retrieval time, URL, source name, adjustment basis, and SHA-256 hash. A value
with an incompatible observation date, corporate-action basis, or instrument
identifier must be reported as `not_comparable`.

## Primary-source findings

- [Upstox Historical Candle Data V3](https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/)
  documents authenticated daily historical OHLC retrieval and states daily
  availability from 2000, subject to its API access requirements.
- [NSE security-wise historical reports](https://www.nseindia.com/report-detail/eq_security)
  and [daily/monthly capital-market archives](https://www.nseindia.com/resources/historical-reports-capital-market-daily-monthly-archives)
  are official candidates for a second-source OHLC check. An attempted official
  API request for TCS on 2026-09-18 returned HTTP 503, so no comparison value
  is recorded.
- [NSE data policy](https://www.nseindia.com/static/market-data/nse-data-policy)
  and [terms of use](https://www.nseindia.com/static/nse-terms-of-use) require
  the intended storage and redistribution rights to be established before a
  locally tracked benchmark claims permitted reuse. Keep the current status as
  `restricted/pending permission`.

## Benchmark classification

Until a second matching source and explicit storage/usage record are saved,
provider agreement remains `not measured`. A stronger-model judge may supply
an automated proxy label, but results must be labeled `judge-evaluated`; it
does not create human-ground-truth or market-quality evidence by itself.
