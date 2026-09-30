# Robot Intelligence Security Contract

Robot Intelligence is a read-only Jarvis capability. It uses the existing
JarvisService, ToolRegistry, SecurityManager, AuditLog, and ModelRouter
authority. The canonical route is marked `READ_ONLY`, `NO_SIDE_EFFECT`, and
`NO_TRADING`.

This boundary contains no MT5 connector, process launch, Strategy Tester,
MQL5 compiler, order operation, EA attach, AutoTrading mutation, provider
call, credential access, voice path, or database migration.

Important requests retain request/correlation context, robot identity, market
snapshot identity, evidence provenance, and read status. Trading remains a
separate future approval boundary.
