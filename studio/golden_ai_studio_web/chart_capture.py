"""
Golden AI - Chart Capture & AI Analysis
Captura screenshot do gráfico MT5 e envia para IA analisar Price Action.
"""
import os
import sys
import json
import base64
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

ROOT = Path(
    os.environ.get("GOLDENAI_ROOT")
    or Path(__file__).resolve().parents[2]
).resolve()
MT5_TERMINAL = Path(r"C:\Users\Anderson\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075")
SCREENSHOTS_DIR = ROOT / "config" / "chart_screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT PARA ANÁLISE DE PRICE ACTION
# ═══════════════════════════════════════════════════════════════

PRICE_ACTION_PROMPT = """Você é um analista técnico profissional especializado em **Price Action Puro**.

Analise este gráfico de trading e forneça uma análise completa focada APENAS em Price Action:

## 📊 O que analisar:

### 1. TENDÊNCIA
- Tendência atual (Alta, Baixa, Lateral)
- Força da tendência (Fraca, Moderada, Forte)
- Ponto de mudança de tendência

### 2. ZONAS DE SUPORTE E RESISTÊNCIA
- Identifique as zonas mais importantes (mínimo 2-3)
- Marque os preços exatos
- Indique a força de cada zona (Forte, Média, Fraca)

### 3. PADRÕES DE CANDLE
- Identifique qualquer padrão de candle visível
- Martelo, Estrela Cadente, Engolfo, Doji, etc.
- Indique a direção do sinal

### 4. ESTRUTURA DO MERCADO
- Higher Highs / Higher Lows (Tendência de Alta)
- Lower Highs / Lower Lows (Tendência de Baixa)
- Break of Structure (BOS)
- Change of Character (CHoCH)

### 5. ZONAS DE LIQUIDEZ
- Onde estão os stops acumulados
- Falsos rompimentos (Sweeps)
- Fair Value Gaps (FVG) se visíveis

### 6. SUGESTÃO DE OPERAÇÃO
- Direção recomendada (COMPRA/VENDA/AGUARDAR)
- Zona de entrada sugerida
- Stop Loss sugerido (onde colocar)
- Take Profit sugerido (alvos)
- Relação Risco/Retorno

## 📋 Formato da resposta:

Use Markdown com emojis para organizar. Seja específico com preços. 
Não use indicadores técnicos (RSI, MACD, etc.) - APENAS Price Action.

Seja direto e profissional. Dê uma nota de 1 a 10 para a qualidade da configuração."""


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT PARA ANÁLISE DE SCALPING
# ═══════════════════════════════════════════════════════════════

SCALPING_PROMPT = """Você é um **scalper profissional** especializado em entradas rápidas de alta frequência.

Analise este gráfico e identifique oportunidades de **SCALPING** (operações de 5-30 minutos):

## 🎯 FOCO DO SCALPING:

### 1. MOMENTUM CURTO PRAZO
- Direção do momentum nas últimas 3-5 velas
- Velocidade do preço (velas grandes = momentum forte)
- Padrões de continuaão em M1/M5

### 2. ZONAS DE ENTRADA RÁPIDA
- Suporte/Resistência mais próximos ao preço atual
- Máxima/Mínima da sessão atual
- Níveis de preço redondos (1450, 1455, 1460)

### 3. PADRÕES DE SCALPING
- Engolfo de momentum (vela grande na direção)
- Doji de indecisão seguido de ruptura
- Pin bar com pavio longo (rejeição)
- Inside bar quebrada

### 4. GESTÃO DE RISCO SCALPING
- **SL apertado**: 100-200 pontos (10-20 pips)
- **TP rápido**: 100-300 pontos (10-30 pips)
- **Risco/Retorno mínimo**: 1:1.5
- **Tempo máximo**: 30 minutos na operação

### 5. CONDIÇÕES PARA ENTRADA
- Spread baixo (abaixo de 50 pontos)
- Horário de alta liquidez
- Sem notícias importantes em andamento
- Momentum claro (não lateral)

## 📋 RESPOSTA OBRIGATÓRIA:

```json
{
  "direcao": "BUY ou SELL",
  "entrada": 1458.50,
  "stop_loss": 1457.50,
  "take_profit": 1460.00,
  "pontos_risco": 100,
  "pontos_lucro": 150,
  "rr_ratio": 1.5,
  "confianca": 8,
  "tempo_estimado": "10-15 min",
  "motivo": "Engolfo de alta com rejeição no suporte",
  "candle_entrada": "Próxima vela M1",
  "notas": "Entrar apenas se vela M1 fechar verde acima de 1458.30"
}
```

Seja **EXTREMAMENTE ESPECÍFICO** com preços. Responda APENAS em formato JSON válido.
Se não houver oportunidade clara de scalping, retorne: {"direcao": "AGUARDAR", "motivo": "Sem oportunidade"}

⚠️ SCALPING = ENTRADAS RÁPIDAS com SL APERTADO. Não confunda com swing trade."""


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPT PARA ANÁLISE DE SWING TRADE
# ═══════════════════════════════════════════════════════════════

SWING_PROMPT = """Você é um analista de **Swing Trade** especializado em capturar movimentos de médio prazo.

Analise este gráfico e identifique oportunidades de **SWING TRADE** (operações de 1-7 dias):

## 📊 FOCO DO SWING TRADE:

### 1. TENDÊNCIA PRIMÁRIA
- Tendência do timeframe superior (H4/D1)
- Força e direção predominante
- Pontos de inflexão importantes

### 2. ZONAS DE ENTRADA ESTRATÉGICA
- Retrações de Fibonacci (38.2%, 50%, 61.8%)
- Suporte/Resistência de médio prazo
- Médias móveis importantes (20/50/200)

### 3. PADRÕES DE REVERSÃO
- Topo/Fundo duplo
- Ombro-Cabeça-Ombro
- Triângulos de continuação
- Retrações com confirmação

### 4. GESTÃO DE RISCO SWING
- **SL amplo**: 300-800 pontos (30-80 pips)
- **TP estendido**: 600-2000 pontos (60-200 pips)
- **Risco/Retorno mínimo**: 1:2
- **Tempo**: 1-7 dias na operação

### 5. FILTROS DE QUALIDADE
- Trendline de confirmação
- Volume crescente na direção
- Alinhamento com timeframe superior

## 📋 RESPOSTA OBRIGATÓRIA:

```json
{
  "direcao": "BUY ou SELL",
  "entrada": 1458.50,
  "stop_loss": 1445.00,
  "take_profit": 1490.00,
  "pontos_risco": 1350,
  "pontos_lucro": 3150,
  "rr_ratio": 2.3,
  "confianca": 8,
  "tempo_estimado": "2-5 dias",
  "motivo": "Retração 50% fibo + suporte + tendência de alta",
  "candle_entrada": "Fechar acima de 1460.00",
  "notas": "Aguardar confirmação no H4 antes de entrar"
}
```

Seja específico com preços. Responda APENAS em formato JSON válido.
Se não houver oportunidade, retorne: {"direcao": "AGUARDAR", "motivo": "Sem oportunidade"}"""


def find_terminal():
    """Encontra o terminal64.exe"""
    for p in [MT5_TERMINAL / "terminal64.exe", MT5_TERMINAL.parent / "terminal64.exe",
              Path(r"C:\Program Files\MetaTrader 5\terminal64.exe"),
              Path(r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe")]:
        if p.exists():
            return str(p)
    return None


def capture_chart_mt5(symbol="XAUUSD", timeframe="M15"):
    """
    Captura screenshot do gráfico MT5 usando Python + win32gui.
    Alternativa: usar o MT5 para salvar screenshot via script MQL5.
    """
    try:
        # Método 1: Usar script MQL5 para salvar screenshot
        mql_script = f"""
//+------------------------------------------------------------------+
//| GoldenAI_ChartCapture.mq5                                        |
//+------------------------------------------------------------------+
#property strict
void OnStart()
{{
   string filename = "GoldenAI_Chart_" + _Symbol + "_" + TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS) + ".bmp";
   string path = "GoldenAI_ChartCapture\\\\" + filename;
   
   // Salvar screenshot do gráfico atual
   ChartScreenShot(ChartID(), path, 1920, 1080, ALIGN_RIGHT);
   
   Print("Screenshot salvo: " + path);
}}
"""
        # Salvar script temporário
        script_path = MT5_TERMINAL / "MQL5" / "Scripts" / "GoldenAI_ChartCapture.mq5"
        script_path.write_text(mql_script, encoding='utf-8')
        
        # Criar pasta para screenshots
        capture_dir = MT5_TERMINAL / "MQL5" / "Files" / "GoldenAI_ChartCapture"
        capture_dir.mkdir(parents=True, exist_ok=True)
        
        return {
            "ok": True,
            "method": "mql5_script",
            "script_path": str(script_path),
            "capture_dir": str(capture_dir),
            "message": f"Script criado! Execute no MT5: Charts → GoldenAI_ChartCapture"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def resize_image(filepath, max_width=1200, max_height=800):
    """Redimensiona imagem para enviar para IA"""
    try:
        from PIL import Image
        img = Image.open(filepath)
        
        # Calcular novo tamanho mantendo proporção
        ratio = min(max_width / img.width, max_height / img.height)
        if ratio < 1:
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Salvar como JPEG para reduzir tamanho
        jpeg_path = filepath.with_suffix('.jpg')
        img.save(str(jpeg_path), 'JPEG', quality=85)
        return jpeg_path
    except Exception as e:
        return filepath  # Fallback para original


def capture_chart_windows(symbol="XAUUSD"):
    """
    Captura screenshot usando win32gui (Windows).
    Tira screenshot da janela do MT5.
    """
    try:
        import win32gui
        import win32ui
        import win32con
        import win32api
        from PIL import Image
        
        # Encontrar janela do MT5
        hwnd = None
        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if 'MetaTrader' in title or 'MT5' in title:
                    results.append(hwnd)
        
        windows = []
        win32gui.EnumWindows(enum_callback, windows)
        
        if not windows:
            return {"ok": False, "error": "Janela do MT5 não encontrada. Abra o MetaTrader 5."}
        
        hwnd = windows[0]
        
        # Maximizar janela
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
        
        # Obter dimensões
        rect = win32gui.GetWindowRect(hwnd)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        
        # Capturar screenshot
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        
        saveBitMap = win32ui.CreateBitmap()
        saveBitMap.CreateCompatibleBitmap(mfcDC, width, height)
        saveDC.SelectObject(saveBitMap)
        
        saveDC.BitBlt((0, 0), (width, height), mfcDC, (0, 0), win32con.SRCCOPY)
        
        # Salvar
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chart_{symbol}_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename
        saveBitMap.SaveBitmapFile(saveDC, str(filepath))
        
        # Limpar
        win32gui.DeleteObject(saveBitMap.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        
        # Redimensionar para IA
        resized = resize_image(filepath)
        
        # Converter para base64
        with open(resized, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
        
        return {
            "ok": True,
            "method": "windows_screenshot",
            "filepath": str(resized),
            "filename": resized.name,
            "base64": img_base64,
            "width": width,
            "height": height,
            "size_kb": round(resized.stat().st_size / 1024),
        }
    except ImportError:
        return {"ok": False, "error": "pywin32 não instalado. Execute: pip install pywin32"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def capture_chart_pil():
    """
    Captura screenshot de toda a tela usando PIL.
    Menos preciso, mas funciona sem win32gui.
    """
    try:
        from PIL import ImageGrab
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chart_full_{timestamp}.png"
        filepath = SCREENSHOTS_DIR / filename
        
        # Capturar tela inteira
        screenshot = ImageGrab.grab()
        screenshot.save(str(filepath))
        
        # Converter para base64
        with open(filepath, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode()
        
        return {
            "ok": True,
            "method": "pil_screenshot",
            "filepath": str(filepath),
            "filename": filename,
            "base64": img_base64,
        }
    except ImportError:
        return {"ok": False, "error": "Pillow não instalado. Execute: pip install Pillow"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def analyze_chart_with_ai(image_base64, symbol="XAUUSD", timeframe="M15", provider=None, mode="price_action", current_price=None):
    """
    Envia screenshot para IA analisar.
    Modos: price_action, scalping, swing
    Usa Claude Sonnet 4 via OpenRouter (nuvem) como prioridade.
    Fallback: Qwen2.5 VL local.
    """
    # Selecionar prompt baseado no modo
    if mode == "scalping":
        prompt = SCALPING_PROMPT
        tf_hint = "⚡ SCALPING - Use M1/M5 para entradas rapidas"
    elif mode == "swing":
        prompt = SWING_PROMPT
        tf_hint = "📈 SWING TRADE - Considere H4/D1 para tendencia primaria"
    else:
        prompt = PRICE_ACTION_PROMPT
        tf_hint = "📊 Analise Price Action completa"
    
    # Injetar preco real CRITICO para a IA nao inventar precos
    price_warning = ""
    if current_price:
        price_warning = (f"\n\n⚠️ PRECO ATUAL DO ATIVO: {symbol} = {current_price:.2f} "
                       f"(use ESTE preco como referencia para entrada, SL e TP. "
                       f"NAO invente precos diferentes! "
                       f"Os precos no grafico devem estar PROXIMOS de {current_price:.2f}. "
                       f"Se retornar um preco muito diferente de {current_price:.2f}, sera REJEITADO.)")
    
    full_prompt = f"{prompt}\n\n{tf_hint}\n{price_warning}\n📊 Grafico: {symbol} | Timeframe: {timeframe}\n📅 Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    
    # Carregar API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        try:
            config_path = ROOT / "config" / "api_keys.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding='utf-8'))
                api_key = config.get("openrouter_api_key", "")
        except Exception:
            pass
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8765",
        "X-Title": "Golden AI - Chart Analysis",
    } if api_key else None
    
    image_content = [
        {"type": "text", "text": full_prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
    ]
    
    import time as _time
    _cloud_start = _time.time()
    _CLOUD_MAX_SECONDS = 90  # Max total time for ALL cloud models combined
    
    def _call_openrouter(model_name, timeout=45):
        """Chama OpenRouter com um modelo e retorna analise"""
        if _time.time() - _cloud_start > _CLOUD_MAX_SECONDS:
            print("[CHART] Tempo cloud esgotado (%ds)" % _CLOUD_MAX_SECONDS)
            return None
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": image_content}],
            "max_tokens": 2048,
            "temperature": 0.2,
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            if "choices" in result and result["choices"]:
                return result["choices"][0]["message"]["content"]
        return None
    
    # ═══ ORDEM: ClinePass primeiro (assinatura), depois OpenRouter free, depois local ═══
    # ═══ ClinePass Vision Models (assinatura $9.99/mes) ═══
    CLINEPASS_VISION_MODELS = []
    try:
        from cline_provider import ClineProvider
        _cline = ClineProvider()
        _cline.load_api_key()
        if _cline.api_key:
            CLINEPASS_VISION_MODELS = [
                ('cline-pass/minimax-m3', 'MiniMax M3 (ClinePass)'),       # TESTADO OK com imagem
                ('cline-pass/glm-5.2', 'GLM 5.2 (ClinePass)'),            # TESTADO OK com imagem
            ]
    except Exception:
        pass
    
    # ═══ OpenRouter Free Vision Models ═══
    FREE_VISION_MODELS = [
        ('minimax/minimax-m3:free', 'MiniMax M3 (free)'),                          # 1M ctx - TESTADO OK
        ('nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', 'Nemotron Omni 30B (free)'),  # 256K ctx - TESTADO OK
        ('openrouter/free', 'OpenRouter Free Router'),                              # 200K ctx - auto-select
        ('google/gemma-4-31b-it:free', 'Google Gemma 4 31B (free)'),               # 262K ctx - rate limit 429
        ('google/gemma-4-26b-a4b-it:free', 'Google Gemma 4 26B (free)'),           # 262K ctx - rate limit 429
        ('stealth/ox-alpha', 'Ox Alpha (free)'),                                    # 1M ctx - rate limit 429
    ]
    PAID_VISION_MODELS = [
        ('anthropic/claude-sonnet-4', 'Claude Sonnet 4'),
    ]
    
    def _call_clinepass(model_name, timeout=60):
        """Chama ClinePass API com modelo e retorna analise"""
        if _time.time() - _cloud_start > _CLOUD_MAX_SECONDS:
            return None
        try:
            from cline_provider import ClineProvider
            _cp = ClineProvider()
            _cp.load_api_key()
            if not _cp.api_key:
                return None
            headers_cline = {
                'Authorization': 'Bearer %s' % _cp.api_key,
                'Content-Type': 'application/json',
            }
            payload = {
                'model': model_name,
                'messages': [{'role': 'user', 'content': image_content}],
                'max_tokens': 2048,
                'temperature': 0.2,
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request('https://api.cline.bot/api/v1/chat/completions', data=data, headers=headers_cline)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                if 'data' in result and isinstance(result['data'], dict):
                    result = result['data']
                if 'choices' in result and result['choices']:
                    return result['choices'][0]['message']['content']
        except Exception as e:
            print("[CHART] ClinePass %s erro: %s" % (model_name, str(e)[:80]))
        return None
    
    # ═══ Tentar ClinePass primeiro (assinatura) ═══
    print("[CHART] Iniciando analise (ClinePass=%s, OpenRouter=%s, img=%d bytes)" % (bool(CLINEPASS_VISION_MODELS), bool(api_key), len(image_base64)))
    for model_id, model_name in CLINEPASS_VISION_MODELS:
        elapsed = _time.time() - _cloud_start
        if elapsed > _CLOUD_MAX_SECONDS:
            break
        try:
            print("[CHART] Tentando ClinePass: %s (%.1fs restantes)..." % (model_name, _CLOUD_MAX_SECONDS - elapsed))
            analysis = _call_clinepass(model_id)
            if analysis:
                total = _time.time() - _cloud_start
                print("[CHART] %s OK! (%d chars, %.1fs)" % (model_name, len(analysis), total))
                return {"ok": True, "analysis": analysis, "mode": mode, "model": model_name}
        except Exception as e:
            print("[CHART] %s erro: %s" % (model_name, str(e)[:80]))
            continue
    
    # ═══ Tentar OpenRouter gratuitos ═══
    if headers:
        for model_id, model_name in FREE_VISION_MODELS:
            elapsed = _time.time() - _cloud_start
            if elapsed > _CLOUD_MAX_SECONDS:
                print("[CHART] Saindo do cloud: %.1fs > %ds" % (elapsed, _CLOUD_MAX_SECONDS))
                break
            try:
                print("[CHART] Tentando %s (%.1fs restantes)..." % (model_name, _CLOUD_MAX_SECONDS - elapsed))
                analysis = _call_openrouter(model_id)
                if analysis:
                    total = _time.time() - _cloud_start
                    print("[CHART] %s OK! (%d chars, %.1fs)" % (model_name, len(analysis), total))
                    return {"ok": True, "analysis": analysis, "mode": mode, "model": model_name}
                else:
                    print("[CHART] %s retornou None" % model_name)
            except urllib.error.HTTPError as e:
                body = ''
                try: body = e.read().decode('utf-8', errors='replace')[:100]
                except: pass
                print("[CHART] %s HTTP %d: %s" % (model_name, e.code, body))
                continue
            except Exception as e:
                print("[CHART] %s erro: %s" % (model_name, str(e)[:80]))
                continue
        
        # Tentar modelos pagos
        for model_id, model_name in PAID_VISION_MODELS:
            elapsed = _time.time() - _cloud_start
            if elapsed > _CLOUD_MAX_SECONDS:
                break
            try:
                print("[CHART] Tentando %s (pago)" % model_name)
                analysis = _call_openrouter(model_id)
                if analysis:
                    total = _time.time() - _cloud_start
                    print("[CHART] %s OK! (%d chars, %.1fs)" % (model_name, len(analysis), total))
                    return {"ok": True, "analysis": analysis, "mode": mode, "model": model_name}
            except Exception as e:
                print("[CHART] %s falhou: %s" % (model_name, str(e)[:80]))
                continue
    
    cloud_total = _time.time() - _cloud_start
    print("[CHART] Todos cloud falharam em %.1fs, usando Qwen local" % cloud_total)
    
    # ═══ FALLBACK FINAL: Qwen2.5 VL local (sempre funciona) ═══
    try:
        import ollama
        import base64
        img_bytes = base64.b64decode(image_base64)
        
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[
                {
                    'role': 'user',
                    'content': full_prompt,
                    'images': [img_bytes]
                }
            ]
        )
        
        analysis = response.get('message', {}).get('content', '')
        if analysis:
            print("[CHART] Qwen VL fallback OK (%d chars)" % len(analysis))
            return {"ok": True, "analysis": analysis, "mode": mode, "model": "Qwen2.5 VL (local)"}
        else:
            return {"ok": False, "error": "Resposta vazia do modelo"}
            
    except ImportError:
        return {"ok": False, "error": "Nenhum modelo de visao disponivel. Configure OpenRouter ou instale Ollama."}
    except Exception as e:
        return {"ok": False, "error": f"Erro na analise: {str(e)}"}


def get_current_price(symbol="XAUUSD"):
    """Obtem o preco atual do simbolo via MT5 (mantido vivo)"""
    try:
        import MetaTrader5 as mt5
        try:
            from mt5_connector import ensure_connection
            ensure_connection()
        except ImportError:
            if not mt5.initialize():
                return None
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            return {"bid": tick.bid, "ask": tick.ask, "mid": (tick.bid + tick.ask) / 2}
    except ImportError:
        print("[CHART] MetaTrader5 Python nao instalado")
    except Exception as e:
        print(f"[CHART] Erro ao obter preco: {e}")
    return None


def full_chart_analysis(symbol="XAUUSD", timeframe="M15", mode="price_action"):
    """
    Fluxo completo: captura grafico -> analisa com IA -> retorna resultado.
    Modos: price_action, scalping, swing
    Timeframes automaticos:
      - scalping: M1, M5
      - price_action: M15, M30, H1
      - swing: H1, H4, D1
    """
    try:
        # Override automatico do timeframe baseado no modo
        MODE_TIMEFRAMES = {
            'scalping': ['M1', 'M5'],
            'price_action': ['M15', 'M30', 'H1'],
            'swing': ['H1', 'H4', 'D1'],
        }
        auto_tfs = MODE_TIMEFRAMES.get(mode, ['M15', 'M30', 'H1'])
        # Se o timeframe fornecido nao esta no range do modo, usar o primeiro do modo
        if timeframe not in auto_tfs:
            timeframe = auto_tfs[0]
        
        # 0. Obter preco atual via MT5 para injetar no prompt
        price_info = get_current_price(symbol)
        current_price = price_info["mid"] if price_info else None
        
        # 1. Capturar screenshot
        result = capture_chart_windows(symbol)
        
        if not result.get("ok"):
            # Fallback: tentar com PIL
            result = capture_chart_pil()
        
        if not result.get("ok"):
            # Fallback: criar script MQL5
            try:
                mql_result = capture_chart_mt5(symbol, timeframe)
            except Exception:
                mql_result = {}
            return {
                "ok": False,
                "error": result.get("error", "Nao foi possivel capturar o grafico"),
                "mql5_script": mql_result,
                "suggestion": "Verifique se o MT5 esta aberto e maximizado. Abra o grafico do ativo antes de analisar."
            }
        
        # 2. Analisar com IA (injetar preco real)
        img_base64 = result.get("base64", "")
        if not img_base64:
            return {"ok": False, "error": "Screenshot capturado mas sem dados de imagem"}
        
        analysis = analyze_chart_with_ai(img_base64, symbol, timeframe, mode=mode, current_price=current_price)
        
        return {
            "ok": analysis.get("ok", False),
            "analysis": analysis.get("analysis", ""),
            "model": analysis.get("model", "Desconhecido"),
            "screenshot_path": result.get("filepath", ""),
            "method": result.get("method", ""),
            "symbol": symbol,
            "timeframe": timeframe,
            "recommended_timeframes": auto_tfs,
            "mode": mode,
            "current_price": current_price,
        }
    except Exception as e:
        print(f"[CHART] Erro no full_chart_analysis: {e}")
        return {"ok": False, "error": f"Erro na analise: {str(e)}"}


# Quick test
if __name__ == "__main__":
    result = full_chart_analysis("XAUUSD", "M15")
    print(json.dumps({k: v for k, v in result.items() if k != "analysis"}, indent=2, ensure_ascii=False))
    if result.get("analysis"):
        print("\n=== ANÁLISE ===")
        print(result["analysis"][:1000])

