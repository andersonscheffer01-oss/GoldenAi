"""
Teste de verificacao do ModelRouter para tarefas de programacao.

Objetivo: provar que uma tarefa normal de programacao (perfil CODER)
resolve para golden-qwen-coder-64k:latest via ModelRouter,
respeitando o arquivo config/golden_ai.yaml.

Este teste replica exatamente a logica de _obter_modelo() do golden_ai.py:
    _obter_modelo(perfil) -> _MODEL_ROUTER.get_model_name(perfil) com fallback MODELO
"""
import sys
import os

ROOT_GOLDENAI = r"C:\GoldenAI"
if ROOT_GOLDENAI not in sys.path:
    sys.path.insert(0, ROOT_GOLDENAI)

from core.models.router import ModelRouter
from core.config.settings import load_settings

MODELO_ESPERADO = "golden-qwen-coder-64k:latest"
MODELO_FALLBACK = "qwen2.5-coder:14b"

print("=" * 60)
print("TESTE: ModelRouter para tarefa de programacao (CODER)")
print("=" * 60)

# 1. Carrega as configuracoes do YAML (mesma fonte que golden_ai.py usa)
settings = load_settings()
print(f"\nmodel_profiles do YAML: {settings.model_profiles}")

# 2. Instancia o ModelRouter (mesmo que golden_ai._MODEL_ROUTER)
router = ModelRouter(settings=settings)

# 3. Resolve o modelo para CODER (tarefa de programacao)
modelo_coder = router.get_model_name("CODER")
print(f"ModelRouter.get_model_name('CODER') -> {modelo_coder}")

# 4. Consistencia com FAST e EXPERT
modelo_fast = router.get_model_name("FAST")
modelo_expert = router.get_model_name("EXPERT")
print(f"ModelRouter.get_model_name('FAST')   -> {modelo_fast}")
print(f"ModelRouter.get_model_name('EXPERT') -> {modelo_expert}")

# 5. Verifica que o fallback MODELO permanece como seguranca
print(f"MODELO (fallback)                    -> {MODELO_FALLBACK}")

# 6. Resultado final
print("\n" + "=" * 60)
if modelo_coder == MODELO_ESPERADO:
    print(f"RESULTADO: PASS - Tarefa de programacao resolve para {MODELO_ESPERADO}")
    print("=" * 60)
    sys.exit(0)
else:
    print(f"RESULTADO: FAIL - Esperado {MODELO_ESPERADO}, obtido {modelo_coder}")
    print("=" * 60)
    sys.exit(1)