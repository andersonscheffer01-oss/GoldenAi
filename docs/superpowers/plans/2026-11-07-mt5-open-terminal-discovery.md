# MT5 Open Terminal Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Conectar as leituras de mercado ao terminal MetaTrader 5 aberto, priorizando Hantec, sem operações reais.

**Architecture:** `market_readonly.py` será a única fronteira de descoberta e anexo. Ela enumerará processos já ativos, anexará por caminho, identificará o broker por dados observados e falhará fechado em ambiguidade. `market_data.py` reutilizará essa fronteira, evitando o conector legado que pode iniciar terminal e evitando chamadas de mutação de Market Watch.

**Tech Stack:** Python 3.11+, MetaTrader5 Python API, psutil, pytest, HTTP read models existentes.

**Spec:** `docs/superpowers/specs/2026-11-07-mt5-open-terminal-discovery.md`

## Global Constraints

- `execution_authority=NONE`.
- Somente leitura; nenhum envio de ordem real.
- Não iniciar/encerrar terminal nem alterar símbolos no Market Watch.
- Preservar lógica de entrada, gerenciamento e risco.
- Não ler ou gravar segredos.

## Review Focus

- Nenhum terminal aberto: retornar indisponibilidade sem chamar `initialize`.
- Uma instância Hantec e outras instâncias: escolher somente Hantec.
- Duas instâncias sem Hantec: retornar ambiguidade, sem escolha silenciosa.
- Primeiro candidato falha e outro conecta: tentar o próximo sem auto-launch.
- Caminhos de análise legada: usar o anexo seguro e não chamar `ensure_connection`/`symbol_select`.

### Task 1: Descoberta e anexo read-only do terminal

**Files:**
- Modify: `studio/golden_ai_studio_web/jarvis_core/tools/market_readonly.py`
- Test: `studio/golden_ai_studio_web/tests/test_mt5_open_terminal_discovery.py`
- Update: `studio/golden_ai_studio_web/tests/test_b4_2_market_intelligence.py`

**Interfaces:**
- Produces `_discover_open_mt5_terminals() -> list[dict[str, Any]]` for active process candidates.
- Preserves `_market_data_connection() -> tuple[Any, Any, str]` as the shared read-only attachment boundary.
- Changes `_connection()` to use the shared boundary instead of legacy auto-connection.

- [x] **Step 1: Write failing tests** for Hantec preference, single fallback, ambiguity, no-process no-initialize, and a disconnected candidate.
- [x] **Step 2: Run the new tests and observe failure because discovery/selection is not implemented.**
- [x] **Step 3: Implement process enumeration, broker identity inspection, deterministic selection, fail-closed errors, and safe `_connection()` routing.**
- [x] **Step 4: Run the new tests plus the existing MT5 read-only regression tests.**

### Task 2: Route dashboard analysis reads through the shared connector

**Files:**
- Modify: `studio/golden_ai_studio_web/market_data.py`
- Test: `studio/golden_ai_studio_web/tests/test_mt5_open_terminal_discovery.py`
- Update: `studio/golden_ai_studio_web/tests/test_market_intelligence_readonly.py`

**Interfaces:**
- Consumes `_market_data_connection()` through a public read-only helper.
- Produces the same existing `get_market_overview`, `get_market_chart`, `get_market_tick`, `get_forex_analysis`, and `get_market_ai_context` shapes.

- [x] **Step 1: Add a failing source/behavior test proving legacy market reads do not use `ensure_connection` or `symbol_select`.**
- [x] **Step 2: Run the focused tests and observe failure against the current legacy calls.**
- [x] **Step 3: Replace legacy connection calls with the shared read-only helper and remove Market Watch mutation calls, preserving response shapes.**
- [x] **Step 4: Run focused market, bridge, analysis, and desktop regression tests.**

## Final Verification

- Run Python syntax checks for every changed Python file.
- Run the focused MT5/market/bridge/desktop test set.
- Run `node --check` for any changed JavaScript (expected unchanged).
- Run `git diff --check` and inspect the final diff for forbidden execution paths.

