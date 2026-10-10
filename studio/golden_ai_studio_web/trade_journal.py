#!/usr/bin/env python3
"""
Golden AI - Trade Journal & Setup Database
Registra toda analise, resultado, e aprende com o historico.

Componentes:
  1. TradeJournal - loga cada analise e seu resultado
  2. SetupDatabase - persiste setups para busca estatistica
  3. FeedbackLoop - calibra o score com dados reais
"""

import json
import math
import os
from datetime import date, datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import numpy as np

# ═══════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════

JOURNAL_DIR = Path(r"C:\GoldenAI\data\trade_journal")
SETUP_DB_DIR = Path(r"C:\GoldenAI\data\setup_database")

HISTORY_PAGE_MAX_LIMIT = 10
HISTORY_SCAN_MAX_RECORDS = 10000
HISTORY_RECORD_TYPES = frozenset({
    "ALL", "PENDING_ANALYSIS", "IMPORTED_MT5",
    "EXECUTION_UNVERIFIED", "JOURNAL_RESULT_UNVERIFIED",
})


# ═══════════════════════════════════════════════════════════════
# 1. TRADE JOURNAL
# ═══════════════════════════════════════════════════════════════

@dataclass
class TradeEntry:
    """Entrada do journal - cada analise virou registro"""
    setup_id: str
    strategy_id: str
    setup_name: str
    timestamp: str
    symbol: str
    direction: str  # BUY, SELL, NONE
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward: float
    score: int
    confidence: str
    # Timeframes no momento da analise
    tf_h4_trend: str
    tf_h4_strength: float
    tf_h1_trend: str
    tf_h1_strength: float
    tf_m15_trend: str
    tf_m15_structure: str
    tf_m5_breakout: bool
    tf_m5_retest: bool
    # Indicadores
    rsi_m15: float
    adx_m15: float
    atr_m15: float
    atr_percentile: float
    spread: float
    # Estatisticas no momento
    historical_win_rate: float
    historical_expectancy: float
    historical_samples: int
    # Razoes
    reasons: str  # JSON array
    # IA
    ai_model: str
    ai_analysis: str
    # Resultado (preenchido depois)
    result: str  # 'WIN', 'LOSS', 'BREAKEVEN', 'PENDING'
    result_price: float  # preco de fechamento
    result_time: str
    mfe: float  # Max Favorable Excursion
    mae: float  # Max Adverse Excursion
    actual_rr: float  # R multiplo real
    # Metadados
    trade_opened: bool  # se o trade foi executado
    trade_ticket: int  # ticket no MT5


class TradeJournal:
    """Registra e recupera analises/trades"""

    def __init__(self, journal_dir=None):
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.journal_dir = Path(journal_dir) if journal_dir is not None else JOURNAL_DIR
        self.journal_file = self.journal_dir / f"journal_{self.current_date}.jsonl"

    def log_analysis(self, analysis: Dict, ai_response: str = "", ai_model: str = "") -> str:
        """Registra uma analise completa no journal"""
        ranked_setups = analysis.get('ranked_setups') or []
        best_ranked = ranked_setups[0] if ranked_setups else {}
        strategy_id = (
            analysis.get('strategy_id')
            or analysis.get('setup_key')
            or best_ranked.get('setup_id', '')
        )
        setup_name = (
            analysis.get('setup_name')
            or analysis.get('setup')
            or best_ranked.get('name', '')
        )
        setup_id = "%s_%s_%s" % (
            analysis.get('symbol', 'XAUUSD'),
            datetime.now().strftime("%Y%m%d_%H%M%S"),
            strategy_id or analysis.get('direction', 'NONE')
        )

        # Extrair timeframes
        tfs = analysis.get('timeframes', {})

        entry = TradeEntry(
            setup_id=setup_id,
            strategy_id=strategy_id,
            setup_name=setup_name,
            timestamp=datetime.now().isoformat(),
            symbol=analysis.get('symbol', 'XAUUSD'),
            direction=analysis.get('direction', 'NONE'),
            entry_price=analysis.get('entry', 0),
            stop_loss=analysis.get('stop_loss', 0),
            take_profit_1=analysis.get('take_profit_1', 0),
            take_profit_2=analysis.get('take_profit_2', 0),
            take_profit_3=analysis.get('take_profit_3', 0),
            risk_reward=analysis.get('risk_reward', 0),
            score=analysis.get('score', 0),
            confidence=analysis.get('confidence', 'nao_operar'),
            tf_h4_trend=tfs.get('H4', {}).get('trend', 'lateral'),
            tf_h4_strength=tfs.get('H4', {}).get('strength', 0),
            tf_h1_trend=tfs.get('H1', {}).get('trend', 'lateral'),
            tf_h1_strength=tfs.get('H1', {}).get('strength', 0),
            tf_m15_trend=tfs.get('M15', {}).get('trend', 'lateral'),
            tf_m15_structure=tfs.get('M15', {}).get('structure', 'lateral'),
            tf_m5_breakout=tfs.get('M5', {}).get('breakout', False),
            tf_m5_retest=tfs.get('M5', {}).get('breakout_confirmed', False),
            rsi_m15=tfs.get('M15', {}).get('rsi', 50),
            adx_m15=tfs.get('M15', {}).get('adx', 20),
            atr_m15=tfs.get('M15', {}).get('atr', 0),
            atr_percentile=analysis.get('market_structure', {}).get('atr_percentile', 50),
            spread=analysis.get('market_structure', {}).get('spread', 0),
            historical_win_rate=analysis.get('statistics', {}).get('win_rate', 0),
            historical_expectancy=analysis.get('statistics', {}).get('expectancy', 0),
            historical_samples=analysis.get('statistics', {}).get('sample_size', 0),
            reasons=json.dumps(analysis.get('reasons', []), ensure_ascii=False),
            ai_model=ai_model,
            ai_analysis=ai_response[:2000] if ai_response else '',
            result='PENDING',
            result_price=0,
            result_time='',
            mfe=0,
            mae=0,
            actual_rr=0,
            trade_opened=False,
            trade_ticket=0,
        )

        # Salvar no journal
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        with open(self.journal_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + '\n')

        print("[JOURNAL] Analise registrada: %s" % setup_id)
        return setup_id

    def log_trade_result(self, setup_id: str, result: str, close_price: float,
                         mfe: float = 0, mae: float = 0, actual_rr: float = 0):
        """Atualiza o resultado de um trade"""
        updated = False
        for journal_file in sorted(JOURNAL_DIR.glob("journal_*.jsonl"), reverse=True):
            if not journal_file.exists():
                continue
            entries = []
            file_updated = False
            with open(journal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get('setup_id') == setup_id:
                            entry['result'] = result
                            entry['result_price'] = close_price
                            entry['result_time'] = datetime.now().isoformat()
                            entry['mfe'] = mfe
                            entry['mae'] = mae
                            entry['actual_rr'] = actual_rr
                            file_updated = True
                            updated = True
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue

            if file_updated:
                with open(journal_file, 'w', encoding='utf-8') as f:
                    for entry in entries:
                        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                break

        if not updated:
            print("[JOURNAL] Setup nao encontrado para atualizar: %s" % setup_id)
            return False

        print("[JOURNAL] Resultado atualizado: %s -> %s" % (setup_id, result))
        return True

    def get_recent_entries(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """Busca entradas recentes do journal"""
        entries = []
        for journal_file in sorted(JOURNAL_DIR.glob("journal_*.jsonl"), reverse=True):
            if not journal_file.exists():
                continue
            with open(journal_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if symbol and entry.get('symbol') != symbol:
                            continue
                        entries.append(entry)
                        if len(entries) >= limit:
                            return entries
                    except json.JSONDecodeError:
                        continue
        return entries

    @staticmethod
    def _iter_jsonl_reverse(path, chunk_size=65536):
        with path.open("rb") as source:
            position = source.seek(0, os.SEEK_END)
            pending = b""
            while position:
                size = min(chunk_size, position)
                position -= size
                source.seek(position)
                parts = (source.read(size) + pending).split(b"\n")
                pending = parts[0]
                for line in reversed(parts[1:]):
                    if line.strip():
                        yield line.decode("utf-8", errors="replace")
            if pending.strip():
                yield pending.decode("utf-8", errors="replace")

    @staticmethod
    def _history_projection(entry):
        model = str(entry.get("ai_model") or "").strip().upper()
        confidence = str(entry.get("confidence") or "").strip().upper()
        rr_source = str(entry.get("rr_source") or "").strip().upper()
        imported = (model == "MT5_IMPORT" or confidence.startswith("IMPORTED")
                    or rr_source.startswith("MT5_IMPORT"))
        result = str(entry.get("result") or "").strip().upper()
        pending = result in {"", "PENDING"}
        execution_claim = (model == "AUTO_TRADE" or entry.get("trade_opened") is True
                           or (isinstance(entry.get("trade_ticket"), int)
                               and not isinstance(entry.get("trade_ticket"), bool)
                               and entry.get("trade_ticket", 0) > 0))

        if imported:
            record_type, execution_status = "IMPORTED_MT5", "NOT_REAL_ACCOUNT_VERIFIED"
        elif execution_claim:
            record_type, execution_status = "EXECUTION_UNVERIFIED", "UNVERIFIED"
        elif pending:
            record_type, execution_status = "PENDING_ANALYSIS", "NOT_EXECUTED"
        else:
            record_type, execution_status = "JOURNAL_RESULT_UNVERIFIED", "UNVERIFIED"

        allowed = (
            "setup_id", "timestamp", "symbol", "direction", "result",
            "entry_price", "result_price", "result_time", "actual_rr",
        )
        projected = {"record_type": record_type,
                     "execution_status": execution_status,
                     "exit_type": "NOT_RECORDED"}
        for key in allowed:
            value = entry.get(key)
            if (isinstance(value, (str, int, float))
                    and not isinstance(value, bool)
                    and (not isinstance(value, float) or math.isfinite(value))):
                projected["record_id" if key == "setup_id" else key] = (
                    str(value)[:160] if key in {"setup_id", "timestamp", "symbol",
                                                "direction", "result", "result_time"}
                    else value
                )
        return projected

    def get_history_page(self, symbol="", record_type="ALL", limit=10, offset=0,
                         date_from="", date_to="", exit_type="ALL"):
        """Read a bounded, allowlisted Journal page without creating or writing files."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= HISTORY_PAGE_MAX_LIMIT:
            return {"ok": False, "error_code": "INVALID_LIMIT", "read_only": True}
        if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset < HISTORY_SCAN_MAX_RECORDS:
            return {"ok": False, "error_code": "INVALID_OFFSET", "read_only": True}
        kind = str(record_type or "ALL").strip().upper()
        if kind not in HISTORY_RECORD_TYPES:
            return {"ok": False, "error_code": "INVALID_RECORD_TYPE", "read_only": True}
        selected_symbol = str(symbol or "").strip().upper()
        if len(selected_symbol) > 32 or any(
                char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._#-"
                for char in selected_symbol):
            return {"ok": False, "error_code": "INVALID_SYMBOL", "read_only": True}
        bounds = []
        for value in (date_from, date_to):
            if value in (None, ""):
                bounds.append(None)
                continue
            if not isinstance(value, str) or len(value) != 10:
                return {"ok": False, "error_code": "INVALID_DATE", "read_only": True}
            try:
                bounds.append(date.fromisoformat(value))
            except ValueError:
                return {"ok": False, "error_code": "INVALID_DATE", "read_only": True}
        if bounds[0] and bounds[1] and bounds[0] > bounds[1]:
            return {"ok": False, "error_code": "INVALID_DATE_RANGE", "read_only": True}
        selected_exit = str(exit_type or "ALL").strip().upper()
        if selected_exit not in {"ALL", "NOT_RECORDED"}:
            return {"ok": False, "error_code": "UNSUPPORTED_EXIT_FILTER", "read_only": True}

        if self.journal_dir.is_symlink() or not self.journal_dir.is_dir():
            return {"ok": True, "status": "UNAVAILABLE",
                    "reason": "JOURNAL_DIRECTORY_MISSING", "records": [],
                    "count": 0, "limit": limit, "offset": offset,
                    "symbol": selected_symbol,
                    "date_from": date_from or None, "date_to": date_to or None,
                    "date_basis": "RAW_TIMESTAMP_CALENDAR_DATE_NO_TZ_CONVERSION",
                    "exit_type_filter": selected_exit,
                    "has_more": False, "scan_truncated": False,
                    "scanned_records": 0, "read_only": True,
                    "proven_execution_supported": False}

        records = []
        matched = 0
        scanned = 0
        truncated = False
        for path in sorted(self.journal_dir.glob("journal_*.jsonl"), reverse=True):
            if path.is_symlink() or not path.is_file():
                continue
            for line in self._iter_jsonl_reverse(path):
                if scanned >= HISTORY_SCAN_MAX_RECORDS:
                    truncated = True
                    break
                scanned += 1
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(entry, dict):
                    continue
                projection = self._history_projection(entry)
                if selected_symbol and str(projection.get("symbol") or "").upper() != selected_symbol:
                    continue
                if kind != "ALL" and projection["record_type"] != kind:
                    continue
                if selected_exit == "NOT_RECORDED" and projection["exit_type"] != "NOT_RECORDED":
                    continue
                if bounds[0] or bounds[1]:
                    raw_timestamp = projection.get("timestamp", "")
                    raw_date = raw_timestamp[:10] if isinstance(raw_timestamp, str) else ""
                    try:
                        record_date = date.fromisoformat(raw_date)
                        if len(raw_timestamp) > 10:
                            if raw_timestamp[10] not in {"T", " "}:
                                continue
                            datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if bounds[0] and record_date < bounds[0]:
                        continue
                    if bounds[1] and record_date > bounds[1]:
                        continue
                if matched >= offset and len(records) < limit:
                    records.append(projection)
                matched += 1
            if truncated:
                break

        return {"ok": True, "status": "AVAILABLE", "records": records,
                "count": len(records), "limit": limit, "offset": offset,
                "symbol": selected_symbol,
                "date_from": date_from or None, "date_to": date_to or None,
                "date_basis": "RAW_TIMESTAMP_CALENDAR_DATE_NO_TZ_CONVERSION",
                "exit_type_filter": selected_exit,
                "has_more": matched > offset + len(records),
                "scan_truncated": truncated, "scanned_records": scanned,
                "read_only": True, "proven_execution_supported": False}

    def get_statistics(self, symbol: str = None) -> Dict:
        """Calcula estatisticas gerais do journal"""
        entries = self.get_recent_entries(symbol, limit=10000)

        if not entries:
            return {'total': 0, 'total_trades': 0, 'win_rate': 0, 'avg_rr': 0}

        resolved = [e for e in entries if e.get('result') not in ('PENDING', '')]
        if not resolved:
            return {'total': len(entries), 'total_trades': 0, 'pending': len(entries), 'win_rate': 0, 'avg_rr': 0}

        wins = sum(1 for e in resolved if e['result'] == 'WIN')
        losses = sum(1 for e in resolved if e['result'] == 'LOSS')
        breakeven = sum(1 for e in resolved if e['result'] == 'BREAKEVEN')
        total = len(resolved)

        win_rate = (wins / total * 100) if total > 0 else 0
        avg_rr = np.mean([e.get('actual_rr', 0) for e in resolved]) if resolved else 0

        return {
            'total_analyses': len(entries),
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'breakeven': breakeven,
            'win_rate': round(win_rate, 1),
            'avg_rr': round(avg_rr, 2),
            'pending': len(entries) - total,
        }


# ═══════════════════════════════════════════════════════════════
# 2. SETUP DATABASE
# ═══════════════════════════════════════════════════════════════

class SetupDatabase:
    """Persiste e busca setups por padrao"""

    def __init__(self):
        self.db_file = SETUP_DB_DIR / "setups.jsonl"

    def save_setup(self, analysis: Dict, result: str = 'PENDING'):
        """Salva um setup na database"""
        # Criar hash do setup baseado nas condicoes
        setup_hash = self._hash_setup(analysis)

        record = {
            'setup_hash': setup_hash,
            'timestamp': datetime.now().isoformat(),
            'symbol': analysis.get('symbol', 'XAUUSD'),
            'direction': analysis.get('direction', 'NONE'),
            'score': analysis.get('score', 0),
            'confidence': analysis.get('confidence', 'nao_operar'),
            # Condicoes do setup
            'tf_h4': analysis.get('timeframes', {}).get('H4', {}).get('trend', 'lateral'),
            'tf_h1': analysis.get('timeframes', {}).get('H1', {}).get('trend', 'lateral'),
            'tf_m15': analysis.get('timeframes', {}).get('M15', {}).get('trend', 'lateral'),
            'tf_m15_struct': analysis.get('timeframes', {}).get('M15', {}).get('structure', 'lateral'),
            'tf_m5_breakout': analysis.get('timeframes', {}).get('M5', {}).get('breakout', False),
            'tf_m5_retest': analysis.get('timeframes', {}).get('M5', {}).get('breakout_confirmed', False),
            'pullback': analysis.get('timeframes', {}).get('M15', {}).get('pullback', False),
            'volatility': analysis.get('market_structure', {}).get('volatility', 'normal'),
            'atr_percentile': analysis.get('market_structure', {}).get('atr_percentile', 50),
            'in_demand': analysis.get('market_structure', {}).get('in_demand_zone', False),
            'in_supply': analysis.get('market_structure', {}).get('in_supply_zone', False),
            # Resultado
            'result': result,
            'entry': analysis.get('entry', 0),
            'stop_loss': analysis.get('stop_loss', 0),
            'take_profit_1': analysis.get('take_profit_1', 0),
            'risk_reward': analysis.get('risk_reward', 0),
        }

        SETUP_DB_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.db_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

        return setup_hash

    def search_similar(self, symbol: str, direction: str, tf_h4: str, tf_h1: str,
                       pullback: bool, breakout: bool, min_samples: int = 10) -> Dict:
        """Busca setups com condicoes similares"""
        if not self.db_file.exists():
            return {'found': 0, 'win_rate': 0, 'expectancy': 0}

        matches = []
        with open(self.db_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    # Verificar similaridade
                    if (record.get('symbol') == symbol and
                        record.get('direction') == direction and
                        record.get('tf_h4') == tf_h4 and
                        record.get('tf_h1') == tf_h1 and
                        record.get('pullback') == pullback and
                        record.get('tf_m5_breakout') == breakout):
                        matches.append(record)
                except json.JSONDecodeError:
                    continue

        if len(matches) < min_samples:
            return {'found': len(matches), 'sufficient': False}

        resolved = [m for m in matches if m.get('result') in ('WIN', 'LOSS')]
        if not resolved:
            return {'found': len(matches), 'sufficient': False}

        wins = sum(1 for m in resolved if m['result'] == 'WIN')
        total = len(resolved)
        win_rate = (wins / total * 100) if total > 0 else 0

        # Expectancia
        avg_rr_win = np.mean([m.get('risk_reward', 1.5) for m in resolved if m['result'] == 'WIN']) if wins else 0
        losses = total - wins
        avg_rr_loss = 1.0  # Stop = 1R
        expectancy = (win_rate/100 * avg_rr_win) - ((100-win_rate)/100 * avg_rr_loss)

        return {
            'found': len(matches),
            'sufficient': True,
            'win_rate': round(win_rate, 1),
            'expectancy': round(expectancy, 2),
            'avg_rr': round(avg_rr_win, 2) if avg_rr_win else 0,
            'total_wins': wins,
            'total_losses': losses,
        }

    def _hash_setup(self, analysis: Dict) -> str:
        """Gera hash unico do setup"""
        key_parts = [
            analysis.get('symbol', ''),
            analysis.get('direction', ''),
            str(analysis.get('timeframes', {}).get('H4', {}).get('trend', '')),
            str(analysis.get('timeframes', {}).get('H1', {}).get('trend', '')),
            str(analysis.get('timeframes', {}).get('M15', {}).get('trend', '')),
            str(analysis.get('timeframes', {}).get('M15', {}).get('structure', '')),
            str(analysis.get('timeframes', {}).get('M5', {}).get('breakout', '')),
            str(analysis.get('timeframes', {}).get('M15', {}).get('pullback', '')),
        ]
        return '_'.join(key_parts)

    def get_stats_by_score_range(self) -> Dict:
        """Retorna win rate por faixa de score"""
        if not self.db_file.exists():
            return {}

        score_bins = {}
        with open(self.db_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get('result') not in ('WIN', 'LOSS'):
                        continue
                    score = record.get('score', 0)
                    # Definir faixa
                    if score >= 85:
                        bin_key = '85-100'
                    elif score >= 75:
                        bin_key = '75-84'
                    elif score >= 65:
                        bin_key = '65-74'
                    elif score >= 50:
                        bin_key = '50-64'
                    else:
                        bin_key = '0-49'

                    if bin_key not in score_bins:
                        score_bins[bin_key] = {'wins': 0, 'total': 0}
                    score_bins[bin_key]['total'] += 1
                    if record['result'] == 'WIN':
                        score_bins[bin_key]['wins'] += 1
                except json.JSONDecodeError:
                    continue

        # Calcular win rates
        result = {}
        for bin_key, data in sorted(score_bins.items()):
            wr = (data['wins'] / data['total'] * 100) if data['total'] > 0 else 0
            result[bin_key] = {
                'win_rate': round(wr, 1),
                'total': data['total'],
                'wins': data['wins'],
            }
        return result


# ═══════════════════════════════════════════════════════════════
# 3. FEEDBACK LOOP
# ═══════════════════════════════════════════════════════════════

class FeedbackLoop:
    """Calibra o score usando dados reais do historico"""

    def __init__(self):
        self.journal = TradeJournal()
        self.setup_db = SetupDatabase()

    def calibrate_score(self, symbol: str) -> Dict:
        """Calibra o score baseado no historico real"""
        # Buscar stats por faixa de score
        score_stats = self.setup_db.get_stats_by_score_range()

        if not score_stats:
            return {
                'calibrated': False,
                'message': 'Dados insuficientes para calibracao. Necessario minimo de 50 trades resolvidos.'
            }

        # Analisar cada faixa
        calibration = {}
        for bin_key, data in score_stats.items():
            if data['total'] >= 10:  # Minimo 10 trades por faixa
                # Ajustar interpretacao do score
                expected_wr = self._expected_win_rate(bin_key)
                actual_wr = data['win_rate']
                delta = actual_wr - expected_wr

                if delta > 5:
                    adj = 'subestimado'  # Score esta menor que deveria
                elif delta < -5:
                    adj = 'superestimado'  # Score esta maior que deveria
                else:
                    adj = 'calibrado'

                calibration[bin_key] = {
                    'win_rate': actual_wr,
                    'expected_win_rate': expected_wr,
                    'adjustment': adj,
                    'delta': round(delta, 1),
                    'sample_size': data['total'],
                }

        return {
            'calibrated': True,
            'ranges': calibration,
            'total_trades': sum(d['total'] for d in score_stats.values()),
            'message': self._generate_calibration_message(calibration),
        }

    def get_recommendations(self) -> List[str]:
        """Gera recomendacoes baseadas no historico"""
        recommendations = []
        stats = self.journal.get_statistics()

        if stats['total_trades'] < 30:
            recommendations.append(
                "Sistema com apenas %d trades. "
                "Necessario minimo de 30 para confiabilidade estatistica." % stats['total_trades']
            )

        if stats['win_rate'] > 0 and stats['avg_rr'] > 0:
            expectancy = (stats['win_rate']/100 * stats['avg_rr']) - (1 - stats['win_rate']/100)
            if expectancy > 0:
                recommendations.append(
                    "Sistema LUCRATIVO: Expectativa de +%.2fR por trade "
                    "(WR %.1f%%, RR medio %.1f)" % (expectancy, stats['win_rate'], stats['avg_rr'])
                )
            else:
                recommendations.append(
                    "Sistema PERDEDOR: Expectativa de %.2fR por trade. "
                    "Ajuste entradas ou gestao de risco." % expectancy
                )

        # Analise por faixa de score
        score_stats = self.setup_db.get_stats_by_score_range()
        for bin_key, data in sorted(score_stats.items()):
            if data['total'] >= 10:
                if data['win_rate'] >= 65:
                    recommendations.append(
                        "Score %s: %.1f%% WR em %d trades - CONFIÁVEL" % (
                            bin_key, data['win_rate'], data['total']
                        )
                    )
                elif data['win_rate'] < 45:
                    recommendations.append(
                        "Score %s: %.1f%% WR em %d trades - EVITAR" % (
                            bin_key, data['win_rate'], data['total']
                        )
                    )

        return recommendations

    def _expected_win_rate(self, bin_key: str) -> float:
        """Win rate esperado por faixa de score (antes da calibracao)"""
        ranges = {
            '85-100': 70, '75-84': 60, '65-74': 55,
            '50-64': 48, '0-49': 40,
        }
        return ranges.get(bin_key, 50)

    def _generate_calibration_message(self, calibration: Dict) -> str:
        """Gera mensagem da calibracao"""
        if not calibration:
            return "Calibracao indisponivel. Dados insuficientes."

        messages = []
        for bin_key, data in sorted(calibration.items()):
            if data['adjustment'] == 'subestimado':
                messages.append("Score %s esta SUBESTIMADO (WR real %.1f%% > esperado %.1f%%)" % (
                    bin_key, data['win_rate'], data['expected_win_rate']
                ))
            elif data['adjustment'] == 'superestimado':
                messages.append("Score %s esta SUPERESTIMADO (WR real %.1f%% < esperado %.1f%%)" % (
                    bin_key, data['win_rate'], data['expected_win_rate']
                ))

        return '; '.join(messages) if messages else "Scores calibrados corretamente."


# ═══════════════════════════════════════════════════════════════
# INSTANCIAS GLOBAIS
# ═══════════════════════════════════════════════════════════════

journal = TradeJournal()
setup_db = SetupDatabase()
feedback = FeedbackLoop()
