import sys
sys.path.insert(0, r'C:\GoldenAI')

from core.computer import find_mt5_installations, list_mt5_eas

print("MT5 Installations:", find_mt5_installations())
print()
print("Total EAs:", len(list_mt5_eas()))