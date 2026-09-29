# Jarvis / Golden B3 Product Read Models

## Overview

The overview remains a summary. Detailed domains are loaded independently so a
partial provider does not make unrelated panels look healthy. Counts are shown
only when supplied by the source; missing values remain `UNKNOWN`.

## Market Intelligence

The Radar detail read model supplies market map, asset groups, news, macro,
calendar, sessions, technical state, support/resistance, ranking, validation,
performance, replay metadata, source integrity, and freshness. The UI selects a
symbol and timeframe but does not calculate indicators or alter provider state.

## Scanner and Opportunity

The scanner projection preserves normalized symbol, asset class, mode, direction,
price, spread, score, readiness, regime, volatility, session, trends,
selected/alternative setups, risk-reward, confluence, conditions, indicators,
support/resistance, and raw fields. A selected row opens a read-only detail view.

## Robots and Evidence

Robot rows show identity, source and compiled artifact presence, backtest/test
evidence counts, and lifecycle. Detail data is retrieved through the existing
Robot Catalog owner. Historical evidence remains visible when association is
unresolved; no weak heuristic is introduced by the UI.

Validation and tester evidence keep their evidence classes:
`VERIFIED_REAL_EVIDENCE`, `HISTORICAL_EVIDENCE`, `CALCULATED`, `SYNTHETIC`,
`DEMO`, and `UNKNOWN`.

## Scientific Memory

The first product view shows canonical status, authority, graph summary,
contract types, and the existing relation/gap matrix. It does not import legacy
records, migrate schema, or invent confidence values. Missing confidence is
rendered as `UNKNOWN`.

## Provenance

The provenance table is a compact view of source module/provider, freshness,
availability, and content fingerprint. Full payloads stay behind the existing
read model boundary and secrets are never serialized.

## Refresh and Security

Refresh is an explicit read request through `Gateway -> server_agent.py ->
JarvisService.execute_tool`. Rendering is not an audit write and no endpoint
used by B3 authorizes trading, order sending, MT5 mutation, Strategy Tester
execution, MQL5 compilation, or robot lifecycle changes.
