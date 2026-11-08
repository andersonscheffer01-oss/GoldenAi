# Golden JARVIS Desktop — pacote local do Painel

Este pacote é um snapshot somente leitura da versão que estava rodando em
08/11/2026. O `Jarvis.exe` em `Desktop/Jarvis` é o mesmo binário que estava
aberto nesta máquina; ele carrega o Painel por HTTPS do Core local, em vez de
embutir o HTML atual.

## Conteúdo

- `Desktop/Jarvis/`: aplicativo Windows PyInstaller ONEDIR, pronto para abrir.
- `Source/GoldenAI/`: Core, UI e suporte da mesma árvore local. Extraia esta
  pasta como `C:\GoldenAI` no novo computador, pois o `server_agent.py` usa
  esse caminho canônico.
- `Audit/VERSION_MANIFEST.md`: identificação, hashes, Git e alterações locais.

O pacote não contém `.env`, `config/api_keys.json`, chaves/tokens, credenciais
do MetaTrader, `certs/`, bancos SQLite, logs, `device_registry` ou relatórios
privados da Arena. Também não contém os artefatos MQL5. O Painel continua
somente leitura/simulação com `execution_authority=NONE`.

## Instalação em outro Windows

1. Extraia o ZIP em uma pasta temporária, por exemplo
   `C:\GoldenJarvisLocalPanel-20261108`.
2. Em uma máquina nova (ou em uma instalação separada), copie
   `Source\GoldenAI` para `C:\GoldenAI`. Não sobreponha um GoldenAI existente
   sem fazer backup e sem aprovação.
3. Instale Python 3.13 x64 e crie o ambiente:

   ```powershell
   cd C:\GoldenAI
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r .\requirements-runtime.txt
   ```

   `requirements-runtime.txt` inclui o `requirements.txt` original e
   `aiohttp`, usado pelo gateway HTTPS/pairing. O Desktop já traz PySide6/Qt
   dentro de `_internal`; Python é necessário para o Core.

## HTTPS local

Os certificados são deliberadamente gerados no computador de destino. Com o
Core parado, execute no novo Windows:

```powershell
cd C:\GoldenAI\studio\golden_ai_studio_web
..\..\.venv\Scripts\python.exe -m jarvis_core.ssl_context init
..\..\.venv\Scripts\python.exe -m jarvis_core.ssl_context status
```

Isso cria uma CA local e um certificado de servidor em `C:\GoldenAI\certs`.
Nunca copie certificados privados desta máquina para o pacote. Se o navegador
ou o Windows precisar confiar na CA local, o operador pode executar, por sua
conta, `..\..\.venv\Scripts\python.exe -m jarvis_core.ssl_context add-trust`.
Esse passo altera apenas o repositório de certificados do usuário do Windows.

## Abrir em modo seguro

Para manter o gateway apenas no computador novo, inicie o Core manualmente
antes do Desktop:

```powershell
cd C:\GoldenAI\studio\golden_ai_studio_web
$env:GOLDEN_SSL='1'
$env:GOLDEN_GATEWAY_LAN='0'
$env:JARVIS_MCP_AUTOSTART='0'
..\..\.venv\Scripts\python.exe .\server_agent.py --port 8765 --runtime-profile web-ai-safe
```

Em outra janela, abra com duplo clique:

```text
C:\GoldenJarvisLocalPanel-20261108\Desktop\Jarvis\Jarvis.exe
```

O perfil `web-ai-safe` habilita apenas leitura de mercado quando disponível e
mantém `mt5_enabled`, `trading_enabled`, teste de estratégia e compilação MQL5
desabilitados. Não conecte credenciais do MetaTrader para esta validação e não
envie ordens.

## Pareamento

No primeiro uso em cada Windows, o Desktop faz o pareamento local contra
`https://127.0.0.1:8766/pairing/code` e
`https://127.0.0.1:8766/pairing/confirm`. Se uma identidade antiga não for
validada, ele solicita outra automaticamente. O token fica protegido por
DPAPI nas configurações do usuário (`GoldenAI/JarvisDesktop`) e não é copiado
para este pacote. O gateway de pareamento aceita a solicitação somente de
localhost.

## Conferência do Painel

1. Confirme que `https://127.0.0.1:8765/health` responde `200`.
2. Abra o `Jarvis.exe`, selecione `Painel` e confirme as seções:
   `Análise Profunda do Ativo`, `Monitoramento contínuo do ativo` e
   `Plano condicional monitorado`.
3. Confirme os indicadores de leitura/simulação e a ausência de qualquer
   execução. O código servido atual importa `src/desktop-shell.js`, onde essas
   três seções são renderizadas.

## O que ainda precisa ser validado no computador de destino

Este pacote foi validado estruturalmente e no runtime desta máquina. Ainda é
necessário confirmar no novo Windows: confiança da CA, inicialização do Core,
pareamento DPAPI, renderização visual em primeiro plano, aceleração Qt e,
se desejado, leitura de dados de mercado. MT5, contas, ordens e lógica de
trading não foram testados nem são necessários para conferir o Painel.
