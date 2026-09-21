import sys
sys.path.insert(0, r'C:\GoldenAI')

try:
    from core.computer import detect_all_mt5_installations
    print('Import OK')
    
    insts = detect_all_mt5_installations()
    print(f'Found {len(insts)} MT5 installations')
    
    for inst in insts:
        print(f'  - {inst.terminal_id}: {inst.name}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()