# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Tickers containing `&` (for example `M&M.NS`, `L&TFH.NS`, `J&KBANK.NS`) are now accepted.
- Technical analysis reports the MACD line as `MACD_12_26_9`, with the signal line and
  histogram as separate `MACD_SIGNAL_12_26_9` and `MACD_HIST_12_26_9` outputs. Previously
  the histogram was reported as the MACD value.
- Technical analysis drops invalid OHLCV rows and reports the count in
  `metadata.dropped_rows`, instead of aborting on a single bad row. It still fails when
  more than 2% of rows are invalid.
- Experiment simulation sizes buys to fit cash after costs, so a full-weight target with
  non-zero costs now trades. Skipped orders are recorded in `SimulationResult.rejections`.

### Added

- `CHANGELOG.md` and `CONTRIBUTING.md`.

## [0.1.0]

### Added

- Initial CLI-first financial research system: provider adapters, deterministic
  fundamental and technical analysis, bounded agent loop, offline experiments runtime,
  and evaluation tooling.
