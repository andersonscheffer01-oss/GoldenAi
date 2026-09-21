import sys
import os
sys.path.insert(0, r'C:\GoldenAI')

# Import from core directly to avoid running the main loop
from core.computer import (
    find_mt5_installations,
    get_mt5_status,
    list_mt5_eas,
    detect_all_mt5_installations,
    get_mt5_installation_by_id,
    list_mt5_experts_for_terminal,
    find_mt5_file_by_name,
    find_mt5_ex5_by_name,
    get_mt5_file_metadata,
    deploy_to_mt5,
    list_mt5_ex5_files,
)

print("=" * 76)
print("TESTE DE INTEGRACAO MT5 - GOLDEN AI V1")
print("=" * 76)
print()

# Test 1: Detect MT5 installations
print("TESTE 1: Detectar MT5")
print("-" * 40)
installations = find_mt5_installations()
print(f"Instalacoes encontradas: {len(installations)}")
for inst in installations:
    print(f"  - {inst}")
print()

# Test 2: Get MT5 status
print("TESTE 2: Status MT5")
print("-" * 40)
status = get_mt5_status()
print(f"MT5 aberto: {status.get('mt5_running')}")
print(f"MetaEditor aberto: {status.get('metaeditor_running')}")
print(f"Instalacoes: {len(status.get('installations', []))}")
print()

# Test 3: Detect all MT5 installations with full info
print("TESTE 3: Instalacoes MT5 completas")
print("-" * 40)
all_insts = detect_all_mt5_installations()
print(f"Instalacoes completas: {len(all_insts)}")
for inst in all_insts:
    print(f"  Terminal ID: {inst.terminal_id}")
    print(f"    Nome: {inst.name}")
    print(f"    Path: {inst.path}")
    print(f"    MQL5: {inst.mql5_path}")
    print(f"    Experts: {inst.experts_path}")
    print(f"    Terminal EXE: {inst.terminal_exe}")
    print(f"    MetaEditor EXE: {inst.metaeditor_exe}")
    print()

# Test 4: List EAs
print("TESTE 4: Listar EAs")
print("-" * 40)
eas = list_mt5_eas()
print(f"Total de EAs: {len(eas)}")
for ea in eas[:5]:
    print(f"  - {ea}")
if len(eas) > 5:
    print(f"  ... e mais {len(eas) - 5}")
print()

# Test 5: Find file by name
print("TESTE 5: Localizar arquivo por nome")
print("-" * 40)
bot_ciclos = find_mt5_file_by_name("Bot Ciclos EA")
print(f"'Bot Ciclos EA' encontrado: {bot_ciclos}")
print()

# Test 6: Get file metadata
print("TESTE 6: Metadados de arquivo")
print("-" * 40)
if bot_ciclos:
    metadata = get_mt5_file_metadata(bot_ciclos)
    print(f"Metadados: {metadata}")
print()

# Test 7: List EX5 files
print("TESTE 7: Listar arquivos EX5")
print("-" * 40)
ex5_files = list_mt5_ex5_files()
print(f"Total de EX5: {len(ex5_files)}")
for ex5 in ex5_files[:5]:
    print(f"  - {ex5}")
print()

# Test 8: Find EX5 by name
print("TESTE 8: Localizar EX5 por nome")
print("-" * 40)
robo_ex5 = find_mt5_ex5_by_name("robo_teste")
print(f"'robo_teste.ex5' encontrado: {robo_ex5}")
print()

print("=" * 76)
print("TODOS OS TESTES CONCLUIDOS")
print("=" * 76)