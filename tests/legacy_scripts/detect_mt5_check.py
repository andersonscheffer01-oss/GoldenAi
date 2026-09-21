import os, sys
sys.path.insert(0, r'C:\GoldenAI')
from core.computer.mt5_tools import find_mt5_installations, get_mt5_status, list_mt5_terminals, list_mt5_eas

print("=== INSTALACOES MT5 ===")
inst = find_mt5_installations()
for i in inst:
    print(i)
print()

print("=== STATUS MT5 ===")
status = get_mt5_status()
print("mt5_running:", status["mt5_running"])
print("metaeditor_running:", status["metaeditor_running"])
print("installations:", status["installations"])
print()

print("=== TERMINAIS ===")
terms = list_mt5_terminals()
for t in terms:
    print(t)
print()

print("=== EAS ===")
eas = list_mt5_eas()
print("Total EAs:", len(eas))
for ea in eas[:10]:
    print("  -", ea)
if len(eas) > 10:
    print("  ... e mais", len(eas) - 10)
