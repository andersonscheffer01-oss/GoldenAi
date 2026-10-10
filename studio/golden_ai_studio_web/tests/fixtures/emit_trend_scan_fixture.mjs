import { emitPendingScan } from "./trend_scan_v1_fixture.mjs";
process.stdout.write(JSON.stringify(await emitPendingScan()));
