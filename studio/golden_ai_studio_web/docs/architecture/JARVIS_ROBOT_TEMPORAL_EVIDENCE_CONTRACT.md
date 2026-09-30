# Robot Temporal Evidence Contract

Suitability links to a B4.2 `snapshot_id` and keeps the evidence row or run
identity as the outcome link. The market context used for an observation is
immutable in the projection; revised evidence is a new artifact or snapshot,
not a silent rewrite of historical context.

Historical labels must not use future outcomes. The read model records label
status and method, separates evidence types, excludes duplicate fingerprints,
and marks missing temporal context `UNKNOWN`. It is structurally ready for a
future time-based evaluation split, but no model training occurs in B4.3.
