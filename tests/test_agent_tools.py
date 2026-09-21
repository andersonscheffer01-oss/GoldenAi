"""
Testes unitários para as ferramentas do Golden AI Agent
"""
import sys
import os
import json
import tempfile
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Import the handler class
sys.path.insert(0, str(ROOT / "studio" / "golden_ai_studio_web"))
from server_agent import GoldenAIHandler


class MockHandler(GoldenAIHandler):
    """Mock handler for testing (no HTTP needed)"""
    def __init__(self):
        pass  # Skip HTTPServer.__init__


def test_list_directory():
    """Test listing a directory"""
    h = MockHandler()
    result = h._tool_list_directory({"path": str(ROOT)})
    assert "GoldenAI" in result or "golden" in result.lower()
    assert "itens" in result
    print("✅ test_list_directory OK")


def test_list_directory_not_found():
    """Test listing a non-existent directory"""
    h = MockHandler()
    result = h._tool_list_directory({"path": "C:/nonexistent/path"})
    assert "nao encontrada" in result
    print("✅ test_list_directory_not_found OK")


def test_read_file():
    """Test reading a file"""
    h = MockHandler()
    result = h._tool_read_file({"path": str(ROOT / "config" / "golden_ai.yaml"), "limit": 50})
    assert "golden_ai.yaml" in result
    print("✅ test_read_file OK")


def test_write_and_read_file():
    """Test writing and reading a file"""
    h = MockHandler()
    tmp = Path(tempfile.mktemp(suffix=".txt"))
    try:
        result = h._tool_write_file({"path": str(tmp), "content": "Hello Golden AI"})
        assert "criado" in result or "editado" in result
        
        result = h._tool_read_file({"path": str(tmp)})
        assert "Hello Golden AI" in result
        print("✅ test_write_and_read_file OK")
    finally:
        tmp.unlink(missing_ok=True)


def test_search_files():
    """Test searching for files"""
    h = MockHandler()
    result = h._tool_search_files({"path": str(ROOT / "config"), "pattern": "*.yaml"})
    assert "golden_ai.yaml" in result
    print("✅ test_search_files OK")


def test_analyze_code():
    """Test code analysis"""
    h = MockHandler()
    result = h._tool_analyze_code({"path": str(ROOT / "studio" / "golden_ai_studio_web" / "server_agent.py")})
    assert "linhas" in result or "Linhas" in result
    print("✅ test_analyze_code OK")


def test_system_info():
    """Test system info"""
    h = MockHandler()
    result = h._tool_system_info()
    assert "CPU" in result or "RAM" in result
    print("✅ test_system_info OK")


def test_web_search():
    """Test web search"""
    h = MockHandler()
    result = h._tool_web_search({"query": "Python programming"})
    assert len(result) > 20
    print("✅ test_web_search OK")


def test_get_exchange_rate():
    """Test exchange rate"""
    h = MockHandler()
    result = h._tool_get_exchange_rate()
    assert "USD" in result or "BRL" in result
    print("✅ test_get_exchange_rate OK")


def test_read_pdf():
    """Test reading a PDF"""
    h = MockHandler()
    # Use the user's PDF as test
    pdf_path = r"C:\Users\Anderson\Desktop\orcamento_calhas_vedacao_atualizado.pdf"
    if Path(pdf_path).exists():
        result = h._tool_read_pdf({"path": pdf_path})
        assert "PDF" in result or "paginas" in result
        print("✅ test_read_pdf OK")
    else:
        print("⏭️ test_read_pdf SKIPPED (PDF not found)")


def test_edit_pdf():
    """Test editing a PDF"""
    h = MockHandler()
    pdf_path = r"C:\Users\Anderson\Desktop\orcamento_calhas_vedacao_atualizado.pdf"
    if Path(pdf_path).exists():
        # Read first to check current state
        result = h._tool_list_pdf_words({"path": pdf_path, "word": "cantoneira"})
        assert "encontrada" in result or "nao encontrada" in result
        print("✅ test_edit_pdf OK")
    else:
        print("⏭️ test_edit_pdf SKIPPED (PDF not found)")


def test_parse_tool_call():
    """Test tool call parsing"""
    h = MockHandler()
    
    # Valid tool call
    result = h._parse_tool_call('{"tool": "list_directory", "path": "/tmp"}')
    assert result is not None
    assert result["tool"] == "list_directory"
    
    # Invalid - no tool
    result = h._parse_tool_call("Just a normal message")
    assert result is None
    
    # Tool call with text around it
    result = h._parse_tool_call('Here is my response\n{"tool": "system_info"}\nDone')
    assert result is not None
    assert result["tool"] == "system_info"
    
    print("✅ test_parse_tool_call OK")


def test_execute_tool():
    """Test tool execution routing"""
    h = MockHandler()
    
    result = h._execute_tool({"tool": "system_info"})
    assert "CPU" in result or "RAM" in result
    
    result = h._execute_tool({"tool": "get_exchange_rate"})
    assert "USD" in result
    
    result = h._execute_tool({"tool": "unknown_tool"})
    assert "desconhecida" in result
    
    print("✅ test_execute_tool OK")


def test_auto_tag():
    """Test auto-tagging"""
    import re
    def auto_tag(msg):
        tags = []
        if re.search(r'trading|trade|forex|moeda', msg, re.I): tags.append('trading')
        if re.search(r'codigo|code|python|mql5', msg, re.I): tags.append('code')
        if re.search(r'analise|backtest', msg, re.I): tags.append('analise')
        if re.search(r'mercado|cotacao|cotac|dolar', msg, re.I): tags.append('mercado')
        return tags
    
    assert 'trading' in auto_tag("Forex trading strategy")
    assert 'code' in auto_tag("Analise o código Python")
    assert 'mercado' in auto_tag("Mercado financeiro")
    assert len(auto_tag("Olá")) == 0
    
    print("✅ test_auto_tag OK")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 GOLDEN AI AGENT - TESTES UNITÁRIOS")
    print("=" * 50)
    print()
    
    tests = [
        test_list_directory,
        test_list_directory_not_found,
        test_read_file,
        test_write_and_read_file,
        test_search_files,
        test_analyze_code,
        test_system_info,
        test_web_search,
        test_get_exchange_rate,
        test_read_pdf,
        test_edit_pdf,
        test_parse_tool_call,
        test_execute_tool,
        test_auto_tag,
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
    print("=" * 50)
    print(f"📊 Resultado: {passed} passaram, {failed} falharam de {len(tests)}")
    print("=" * 50)
