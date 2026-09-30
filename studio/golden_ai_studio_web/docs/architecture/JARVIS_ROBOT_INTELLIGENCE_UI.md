# Robot Intelligence Control Center UI

The existing Control Center keeps the Robot Catalog and adds a read-only
Market Suitability projection under the same Robots surface. It shows robot
identity, repertoire state, evidence strength, structural suitability,
explanations, unknowns, and provenance.

The UI visibly states `ANALYSIS ONLY` and `NOT_GRANTED`. It supports empty,
unknown, disabled, partial, and unavailable states without converting missing
data to zeros. No activate, attach, trade, or AutoTrading action is exposed.

The approved Golden `market.html` surface is unchanged.
