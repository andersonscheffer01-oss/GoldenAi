# Strategy Tester Artifact Contract

Configuration bytes are deterministic UTF-8 without BOM and with LF line
endings. The semantic contract requires `Optimization=0`, `UseRemote=0`,
`UseCloud=0`, `AllowLiveTrading=0`, `AllowDllImport=0` and a shutdown-only
tester mode. The bytes are read back and hashed before a process could start.

Result discovery is bounded to the approved run basename and explicitly
provided agent roots. Missing output is `RESULT_ARTIFACT_MISSING`; more than
one exact candidate is `RESULT_ARTIFACT_AMBIGUOUS`. There is no whole-disk
search or filename-only historical association.
