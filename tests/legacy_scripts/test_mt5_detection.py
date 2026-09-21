import sys
sys.path.insert(0, r'C:\GoldenAI')
from core.computer import detect_all_mt5_installations, get_mt5_installation_by_id, list_mt5_experts_for_terminal

print('=== INSTALACOES MT5 DETECTADAS ===')
insts = detect_all_mt5_installations()
for inst in insts:
    print(f'Terminal ID: {inst.terminal_id}')
    print(f'  Nome: {inst.name}')
    print(f'  Path: {inst.path}')
    print(f'  MQL5: {inst.mql5_path}')
    print(f'  Experts: {inst.experts_path}')
    print(f'  Terminal EXE: {inst.terminal_exe}')
    print(f'  MetaEditor EXE: {inst.metaeditor_exe}')
    print()

if insts:
    print('=== EAs NO TERMINAL PRINCIPAL ===')
    eas = list_mt5_experts_for_terminal(insts[0].terminal_id)
    print(f'Total: {len(eas)}')
    for ea in eas[:5]:
        print(f'  - {ea}')