"""
Testes unitários para os módulos extraídos em app/modules/

Cobre: utils, mt5, files, intent, context
"""
import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.utils import (
    normalizar_texto_intencao,
    detectar_idioma_resposta,
    classificar_intencao_conversacional,
    extrair_studio_context_path,
    hash_texto,
    extrair_codigo,
    extrair_nome_mq5,
    normalizar_texto_v110,
    extrair_query_busca,
    _formatar_bytes,
    caminho_seguro,
)
from app.modules.context import CFG, SERVICES
from app.modules.intent import (
    classificar_intencao_usuario,
    pedido_proibe_escrita,
    pergunta_pede_contexto_tecnico,
    pergunta_pede_ferramenta_local,
)
from app.modules.internet import pergunta_pede_internet
from app.modules.mt5 import caminho_seguro_mt5, listar_eas_mt5
from app.modules.files import (
    arquivo_metadados,
    criar_backup,
    restaurar_backup,
    escrever_arquivo,
    listar_projetos,
)
from app.modules.panel import (
    mostrar_painel_comandos,
    listar_robos_painel,
)


# ============================================================
# TESTES: utils.py
# ============================================================

def test_normalizar_texto_intencao():
    """Remove acentos e normaliza para minúsculas."""
    assert normalizar_texto_intencao("Olá Mundo") == "ola mundo"
    assert normalizar_texto_intencao("CÓDIGO") == "codigo"
    assert normalizar_texto_intencao("") == ""
    assert normalizar_texto_intencao(None) == ""
    print("✅ test_normalizar_texto_intencao OK")


def test_detectar_idioma_resposta_pt():
    """Detecta quando a resposta deve ser em português."""
    assert detectar_idioma_resposta("quantas linhas tem esse código") == "pt"
    assert detectar_idioma_resposta("explique o que esse robo faz") == "pt"
    print("✅ test_detectar_idioma_resposta_pt OK")


def test_detectar_idioma_resposta_en():
    """Detecta quando a resposta deve ser em inglês."""
    assert detectar_idioma_resposta("how many lines does this code have") == "en"
    assert detectar_idioma_resposta("explain what this file does") == "en"
    print("✅ test_detectar_idioma_resposta_en OK")


def test_classificar_intencao_conversacional():
    """Classifica intenção corretamente."""
    assert classificar_intencao_conversacional("corrija esse bug") == "CODING_CHANGE"
    assert classificar_intencao_conversacional("quantas linhas tem") == "FILE_METADATA"
    assert classificar_intencao_conversacional("analise esse código") == "FILE_ANALYSIS"
    assert classificar_intencao_conversacional("explique o que faz") == "FILE_EXPLANATION"
    assert classificar_intencao_conversacional("leia o arquivo") == "FILE_READ"
    assert classificar_intencao_conversacional("olá") == "GENERAL_CONVERSATION"
    print("✅ test_classificar_intencao_conversacional OK")


def test_extrair_studio_context_path():
    """Extrai caminho do contexto Studio."""
    msg = "CURRENT_CONTEXT_PATH=C:/arquivo.py\nCURRENT_CONTEXT_NAME=arquivo.py"
    assert extrair_studio_context_path(msg) == "C:/arquivo.py"
    assert extrair_studio_context_path("mensagem normal") is None
    print("✅ test_extrair_studio_context_path OK")


def test_hash_texto():
    """Gera hash SHA-256."""
    h = hash_texto("hello")
    assert len(h) == 64
    assert h == hash_texto("hello")  # Determinístico
    assert h != hash_texto("hello2")
    print("✅ test_hash_texto OK")


def test_extrair_codigo():
    """Extrai código de bloco Markdown."""
    r = extrair_codigo("```python\nprint('hi')\n```")
    assert "print('hi')" in r
    assert extrair_codigo("código simples") == "código simples"
    assert extrair_codigo("") == ""
    assert extrair_codigo(None) == ""
    print("✅ test_extrair_codigo OK")


def test_extrair_nome_mq5():
    """Extrai nome de arquivo .mq5."""
    assert extrair_nome_mq5("analise o arquivo Robo_Test.mq5") == "Robo_Test.mq5"
    assert extrair_nome_mq5("qual a cotação do dólar") is None
    print("✅ test_extrair_nome_mq5 OK")


def test_normalizar_texto_v110():
    """Normalização V1.10."""
    assert normalizar_texto_v110("Pesquise na Internet") == "pesquise na internet"
    assert normalizar_texto_v110("") == ""
    print("✅ test_normalizar_texto_v110 OK")


def test_extrair_query_busca():
    """Extrai query de busca."""
    q = extrair_query_busca("pesquise na internet sobre trailing stop")
    assert "trailing stop" in q
    assert "pesquise" not in q
    print("✅ test_extrair_query_busca OK")


def test_formatar_bytes():
    """Formata bytes."""
    assert _formatar_bytes(500) == "500 B"
    assert "KB" in _formatar_bytes(2048)
    assert "MB" in _formatar_bytes(2 * 1024 * 1024)
    assert "GB" in _formatar_bytes(2 * 1024 * 1024 * 1024)
    print("✅ test_formatar_bytes OK")


def test_caminho_seguro():
    """Valida caminho seguro."""
    # Caminho dentro de PASTA_PROJETOS
    resultado = caminho_seguro("arquivo.py")
    assert resultado is not None
    assert "projetos" in resultado

    # Caminho com traversal
    resultado = caminho_seguro("../../etc/passwd")
    assert resultado is None
    print("✅ test_caminho_seguro OK")


# ============================================================
# TESTES: context.py
# ============================================================

def test_cfg_constants():
    """Verifica que CFG tem as constantes necessárias."""
    assert CFG.MODELO
    assert CFG.PASTA_PROJETOS
    assert CFG.PASTA_BACKUPS
    assert CFG.PASTA_LOGS
    assert CFG.SESSION_ID
    print("✅ test_cfg_constants OK")


def test_obter_modelo():
    """Verifica obter_modelo retorna string."""
    from app.modules.context import obter_modelo
    modelo = obter_modelo()
    assert isinstance(modelo, str)
    assert len(modelo) > 0
    print("✅ test_obter_modelo OK")


# ============================================================
# TESTES: intent.py
# ============================================================

def test_classificar_intencao_usuario():
    """Classifica intenção do usuário."""
    assert classificar_intencao_usuario("corrija o bug") == "ESCRITA"
    assert classificar_intencao_usuario("não altere nada") == "LEITURA"
    assert classificar_intencao_usuario("analise o código") == "LEITURA"
    assert classificar_intencao_usuario("olá, tudo bem?") == "CONVERSA"
    print("✅ test_classificar_intencao_usuario OK")


def test_pedido_proibe_escrita():
    """Verifica se pedido proibe escrita."""
    assert pedido_proibe_escrita("não altere nada") is True
    assert pedido_proibe_escrita("corrija o bug") is False
    print("✅ test_pedido_proibe_escrita OK")


def test_pergunta_pede_contexto_tecnico():
    """Verifica se pergunta pede contexto técnico."""
    assert pergunta_pede_contexto_tecnico("leia o arquivo Python") is True
    assert pergunta_pede_contexto_tecnico("qual a cotação do dólar") is False
    print("✅ test_pergunta_pede_contexto_tecnico OK")


def test_pergunta_pede_ferramenta_local():
    """Verifica se pergunta pede ferramenta local."""
    assert pergunta_pede_ferramenta_local("liste a pasta") is True
    assert pergunta_pede_ferramenta_local("explique o que é forex") is False
    print("✅ test_pergunta_pede_ferramenta_local OK")


# ============================================================
# TESTES: mt5.py
# ============================================================

def test_caminho_seguro_mt5():
    """Valida caminho MT5 seguro."""
    resultado = caminho_seguro_mt5("Meus Robos/teste.mq5")
    # Pode retornar None se a pasta não existir, mas não deve crashar
    assert resultado is None or "Experts" in resultado
    print("✅ test_caminho_seguro_mt5 OK")


def test_listar_eas_mt5():
    """Lista EAs do MT5 (pode retornar mensagem de pasta não encontrada)."""
    resultado = listar_eas_mt5()
    assert isinstance(resultado, str)
    assert len(resultado) > 0
    print("✅ test_listar_eas_mt5 OK")


# ============================================================
# TESTES: files.py
# ============================================================

def test_arquivo_metadados_nao_encontrado():
    """Metadados de arquivo inexistente."""
    resultado = arquivo_metadados("arquivo_que_nao_existe.py")
    assert resultado["ok"] is False
    print("✅ test_arquivo_metadados_nao_encontrado OK")


def test_criar_restaurar_backup():
    """Cria e restaura backup."""
    from app.modules.context import CFG
    projetos = Path(CFG.PASTA_PROJETOS)
    projetos.mkdir(parents=True, exist_ok=True)
    tmp = projetos / "_test_backup_temp.txt"
    try:
        # Cria arquivo
        tmp.write_text("conteudo original", encoding="utf-8")

        # Cria backup
        backup, erro = criar_backup("_test_backup_temp.txt")
        assert erro is None, f"Erro: {erro}"
        assert backup is not None
        assert os.path.isfile(backup)

        # Modifica arquivo
        tmp.write_text("conteudo modificado", encoding="utf-8")

        # Restaura backup
        ok, msg = restaurar_backup("_test_backup_temp.txt", backup)
        assert ok is True

        # Verifica restauração
        assert tmp.read_text(encoding="utf-8") == "conteudo original"

        # Limpa
        os.unlink(backup)
    finally:
        tmp.unlink(missing_ok=True)
    print("✅ test_criar_restaurar_backup OK")


def test_escrever_arquivo():
    """Escreve arquivo com backup automático."""
    from app.modules.context import CFG
    projetos = Path(CFG.PASTA_PROJETOS)
    projetos.mkdir(parents=True, exist_ok=True)
    tmp = projetos / "_test_escrita_temp.txt"
    try:
        # Escreve novo
        ok, backup, msg = escrever_arquivo("_test_escrita_temp.txt", "conteudo novo")
        assert ok is True, f"msg: {msg}"
        assert "salvo" in msg

        # Escreve igual (sem alteração)
        ok, backup, msg = escrever_arquivo("_test_escrita_temp.txt", "conteudo novo")
        assert ok is False
        assert "SEM ALTERACAO" in msg

        # Escreve diferente (com backup)
        ok, backup, msg = escrever_arquivo("_test_escrita_temp.txt", "conteudo alterado")
        assert ok is True
        assert backup is not None

        # Limpa
        if backup and os.path.isfile(backup):
            os.unlink(backup)
    finally:
        tmp.unlink(missing_ok=True)
    print("✅ test_escrever_arquivo OK")


# ============================================================
# TESTES: panel.py
# ============================================================

def test_mostrar_painel_comandos():
    """Mostra painel de comandos."""
    resultado = mostrar_painel_comandos()
    assert "PAINEL DE COMANDOS" in resultado
    assert "listar robos" in resultado
    assert "sair" in resultado
    print("✅ test_mostrar_painel_comandos OK")


def test_listar_robos_painel():
    """Lista robôs do painel."""
    resultado = listar_robos_painel()
    assert isinstance(resultado, str)
    assert len(resultado) > 0
    print("✅ test_listar_robos_painel OK")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("GOLDEN AI - TESTES DOS MODULOS EXTRAIDOS")
    print("=" * 60)
    print()

    tests = [
        # utils
        test_normalizar_texto_intencao,
        test_detectar_idioma_resposta_pt,
        test_detectar_idioma_resposta_en,
        test_classificar_intencao_conversacional,
        test_extrair_studio_context_path,
        test_hash_texto,
        test_extrair_codigo,
        test_extrair_nome_mq5,
        test_normalizar_texto_v110,
        test_extrair_query_busca,
        test_formatar_bytes,
        test_caminho_seguro,
        # context
        test_cfg_constants,
        test_obter_modelo,
        # intent
        test_classificar_intencao_usuario,
        test_pedido_proibe_escrita,
        test_pergunta_pede_contexto_tecnico,
        test_pergunta_pede_ferramenta_local,
        # mt5
        test_caminho_seguro_mt5,
        test_listar_eas_mt5,
        # files
        test_arquivo_metadados_nao_encontrado,
        test_criar_restaurar_backup,
        test_escrever_arquivo,
        # panel
        test_mostrar_painel_comandos,
        test_listar_robos_painel,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"📊 Resultado: {passed} passaram, {failed} falharam de {len(tests)}")
    print("=" * 60)
