# Jarvis / Golden B2 Provenance and Freshness

## Provenance Envelope

B2 read models expose the following stable fields when available:

`source_id`, `provider_id`, `source_type`, `observation_id`,
`correlation_id`, `artifact_id`, `observed_at`, `received_at`, `age`,
`freshness_state`, `evidence_class`, `calculation_origin`,
`content_fingerprint`, and `provenance_chain`.

The content fingerprint is a deterministic SHA-256 over canonical JSON after
recursive secret sanitization. Sensitive keys and credential-like inline values
are replaced with a stable redaction marker before serialization. The digest
is an identity/provenance aid only; it is not an authorization or approval
decision. The correlation identifier is carried through bridge, service, and
HTTP read paths.
The chain records the source and adapter boundary without claiming execution
that did not occur.

## Time Policy

`observed_at` is accepted only from source-provided observation, source, update,
or generation timestamps. The bridge clock may populate `received_at`, but it
must never be used as a substitute observation time. Missing observation time
therefore yields `UNKNOWN` freshness unless the source is unavailable.

`age` is calculated only when both an observation timestamp and a valid current
time are available. Invalid or future source timestamps remain auditable rather
than being silently repaired.

## Freshness Policy

| State | Meaning |
| --- | --- |
| `FRESH` | within the capability/provider freshness window |
| `RECENT` | outside the fresh window but still usable |
| `STALE` | older than the usable window |
| `UNKNOWN` | observation time or capability policy is unavailable |
| `UNAVAILABLE` | provider/capability could not supply data |

Policies are capability-aware. Tick/scanner/radar, macro/news, candles, and
historical evidence have different windows. Provider failure is represented as
`UNAVAILABLE`; it is not converted into an empty successful result.

## Evidence Classes

Only these classifications are emitted by B2: `VERIFIED_REAL_EVIDENCE`,
`HISTORICAL_EVIDENCE`, `CALCULATED`, `SYNTHETIC`, `DEMO`, and `UNKNOWN`.
