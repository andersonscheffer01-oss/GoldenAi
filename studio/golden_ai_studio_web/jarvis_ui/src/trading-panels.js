/**
 * Trading Panels — Read-only trading data display for jarvis-ui
 * 
 * All data routes through Gateway → JarvisService → ToolRegistry.
 * No direct API calls to MT5 endpoints from browser.
 * READ-ONLY: no trade execution, no parameter modification.
 */
(function() {
  'use strict';

  const TradingPanels = {
    /**
     * Fetch and format robot list
     */
    async listRobots() {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const result = await window.Gateway.sendCommand("liste os robôs MT5");
        return this._formatRobotList(result);
      } catch (e) {
        return { error: "Erro ao listar robôs: " + e.message };
      }
    },

    /**
     * Fetch and format scanner/radar results
     */
    async scanMarket() {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const result = await window.Gateway.sendCommand("escaneie o mercado e mostre o radar");
        return this._formatScanner(result);
      } catch (e) {
        return { error: "Erro ao escanear mercado: " + e.message };
      }
    },

    /**
     * Fetch and format backtest results for a specific robot
     */
    async backtest(robotName, options = {}) {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const cmd = `faça backtest do robô ${robotName}`;
        const result = await window.Gateway.sendCommand(cmd);
        return this._formatBacktest(result);
      } catch (e) {
        return { error: "Erro no backtest: " + e.message };
      }
    },

    /**
     * Fetch and format strategy comparison
     */
    async compareStrategies(symbol, strategies) {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const cmd = `compare as estratégias ${strategies.join(", ")} para ${symbol}`;
        const result = await window.Gateway.sendCommand(cmd);
        return this._formatComparison(result);
      } catch (e) {
        return { error: "Erro ao comparar: " + e.message };
      }
    },

    /**
     * Fetch and format validation results
     */
    async validateStrategy(strategyName) {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const cmd = `valide a estratégia ${strategyName}`;
        const result = await window.Gateway.sendCommand(cmd);
        return this._formatValidation(result);
      } catch (e) {
        return { error: "Erro na validação: " + e.message };
      }
    },

    /**
     * Fetch and format risk engine status
     */
    async riskStatus() {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const result = await window.Gateway.sendCommand("mostre o status do risk engine");
        return this._formatRiskStatus(result);
      } catch (e) {
        return { error: "Erro ao consultar risco: " + e.message };
      }
    },

    /**
     * Fetch and format open positions
     */
    async positions() {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const result = await window.Gateway.sendCommand("liste as posições abertas no MT5");
        return this._formatPositions(result);
      } catch (e) {
        return { error: "Erro ao listar posições: " + e.message };
      }
    },

    /**
     * Fetch MT5 account status
     */
    async accountStatus() {
      if (!window.Gateway?.isAuthenticated) return { error: "Gateway não conectado" };
      try {
        const result = await window.Gateway.sendCommand("mostre o status da conta MT5");
        return this._formatAccountStatus(result);
      } catch (e) {
        return { error: "Erro ao consultar conta: " + e.message };
      }
    },

    // ─── Formatters (read-only display) ──────────────────────

    _formatRobotList(result) {
      if (!result || !result.ok) return { text: "Nenhum robô encontrado.", html: "" };
      const robots = result.robots || result.data || [];
      if (!robots.length) return { text: "Nenhum robô encontrado.", html: "" };

      let html = `<div class="tp-section"><h3>Robôs MT5 (${robots.length})</h3>`;
      html += `<div class="tp-grid">`;
      for (const r of robots) {
        const compiled = r.compiled ? "✅" : "❌";
        html += `<div class="tp-card">
          <div class="tp-card-head">${compiled} ${this._esc(r.name || "Sem nome")}</div>
          <div class="tp-card-body">
            <span>${r.lines || 0} linhas</span>
            <span>${r.functions || 0} funções</span>
            <span>${r.size_kb || 0} KB</span>
          </div>
        </div>`;
      }
      html += `</div></div>`;
      return { text: `${robots.length} robôs encontrados.`, html };
    },

    _formatScanner(result) {
      if (!result || !result.ok) return { text: "Scanner indisponível.", html: "" };
      const setups = result.setups || result.radar || [];
      let html = `<div class="tp-section"><h3>Radar de Mercado</h3>`;
      if (setups.length) {
        html += `<table class="tp-table"><tr><th>Ativo</th><th>Setup</th><th>Score</th><th>R:R</th></tr>`;
        for (const s of setups.slice(0, 15)) {
          html += `<tr>
            <td>${this._esc(s.symbol || s.asset || "?")}</td>
            <td>${this._esc(s.setup || s.strategy || "?")}</td>
            <td>${s.score ?? "?"}</td>
            <td>${s.rr ?? s.risk_reward ?? "?"}</td>
          </tr>`;
        }
        html += `</table>`;
      }
      html += `</div>`;
      return { text: `Scanner: ${setups.length} setups encontrados.`, html };
    },

    _formatBacktest(result) {
      if (!result || !result.ok) return { text: "Backtest indisponível.", html: "" };
      const d = result;
      let html = `<div class="tp-section"><h3>Resultado do Backtest</h3>`;
      html += `<div class="tp-stats">`;
      const stats = [
        ["PnL", d.pnl ?? d.profit],
        ["Win Rate", d.win_rate ? d.win_rate + "%" : null],
        ["Trades", d.trades ?? d.total_trades],
        ["Profit Factor", d.profit_factor],
        ["Max Drawdown", d.max_drawdown ? d.max_drawdown + "%" : null],
        ["Return", d.return_pct ? d.return_pct + "%" : null],
      ];
      for (const [label, val] of stats) {
        if (val != null) html += `<div class="tp-stat"><span class="tp-stat-label">${label}</span><span class="tp-stat-value">${val}</span></div>`;
      }
      html += `</div></div>`;
      return { text: `Backtest: PnL ${d.pnl ?? "?"}, Win Rate ${d.win_rate ?? "?"}%.`, html };
    },

    _formatComparison(result) {
      if (!result || !result.ok) return { text: "Comparação indisponível.", html: "" };
      const items = result.results || result.strategies || [];
      let html = `<div class="tp-section"><h3>Comparação de Estratégias</h3>`;
      html += `<table class="tp-table"><tr><th>#</th><th>Estratégia</th><th>PnL</th><th>Win%</th><th>PF</th></tr>`;
      items.sort((a, b) => (b.profit_factor || 0) - (a.profit_factor || 0));
      items.forEach((s, i) => {
        html += `<tr>
          <td>${i + 1}</td>
          <td>${this._esc(s.name || s.strategy || "?")}</td>
          <td>${s.pnl ?? s.profit ?? "?"}</td>
          <td>${s.win_rate ?? "?"}%</td>
          <td>${s.profit_factor ?? "?"}</td>
        </tr>`;
      });
      html += `</table></div>`;
      return { text: `${items.length} estratégias comparadas.`, html };
    },

    _formatValidation(result) {
      if (!result || !result.ok) return { text: "Validação indisponível.", html: "" };
      let html = `<div class="tp-section"><h3>Validação</h3>`;
      if (result.monte_carlo) {
        const mc = result.monte_carlo;
        html += `<div class="tp-sub"><h4>Monte Carlo (${mc.simulations || 1000} sims)</h4>`;
        html += `<p>Ruin probability: ${mc.ruin_probability ?? "?"}%</p>`;
        html += `<p>Median return: ${mc.median_return ?? "?"}%</p></div>`;
      }
      if (result.robustness) {
        const rb = result.robustness;
        html += `<div class="tp-sub"><h4>Robustness Score: ${rb.score ?? "?"}/100</h4>`;
        html += `<p>Verdict: ${rb.verdict ?? "?"}</p></div>`;
      }
      html += `</div>`;
      return { text: `Validação completa. Score: ${result.robustness?.score ?? "?"}/100.`, html };
    },

    _formatRiskStatus(result) {
      if (!result || !result.ok) return { text: "Risk engine indisponível.", html: "" };
      const d = result;
      let html = `<div class="tp-section"><h3>Risk Engine</h3>`;
      html += `<div class="tp-stats">`;
      const stats = [
        ["Balance", d.balance],
        ["Risk/Trade", d.risk_per_trade ? d.risk_per_trade + "%" : null],
        ["Daily PnL", d.daily_pnl],
        ["Open Positions", d.position_count ?? d.open_positions],
        ["News Status", d.news_status],
      ];
      for (const [label, val] of stats) {
        if (val != null) html += `<div class="tp-stat"><span class="tp-stat-label">${label}</span><span class="tp-stat-value">${val}</span></div>`;
      }
      html += `</div></div>`;
      return { text: `Risk: Balance ${d.balance ?? "?"}, ${d.position_count ?? 0} posições abertas.`, html };
    },

    _formatPositions(result) {
      if (!result || !result.ok) return { text: "Nenhuma posição aberta.", html: "" };
      const positions = result.positions || [];
      if (!positions.length) return { text: "Nenhuma posição aberta.", html: "" };
      let html = `<div class="tp-section"><h3>Posições Abertas (${positions.length})</h3>`;
      html += `<table class="tp-table"><tr><th>Ativo</th><th>Tipo</th><th>Volume</th><th>Preço</th><th>PnL</th></tr>`;
      for (const p of positions) {
        html += `<tr>
          <td>${this._esc(p.symbol || "?")}</td>
          <td>${this._esc(p.type || "?")}</td>
          <td>${p.volume ?? "?"}</td>
          <td>${p.price ?? "?"}</td>
          <td class="${(p.pnl || 0) >= 0 ? 'tp-positive' : 'tp-negative'}">${p.pnl ?? "?"}</td>
        </tr>`;
      }
      html += `</table></div>`;
      return { text: `${positions.length} posições abertas.`, html };
    },

    _formatAccountStatus(result) {
      if (!result || !result.ok) return { text: "Conta MT5 indisponível.", html: "" };
      const d = result;
      let html = `<div class="tp-section"><h3>Conta MT5</h3>`;
      html += `<div class="tp-stats">`;
      const stats = [
        ["Account", d.account],
        ["Balance", d.balance],
        ["Equity", d.equity],
        ["Margin", d.margin],
        ["Free Margin", d.free_margin],
        ["Server", d.server],
      ];
      for (const [label, val] of stats) {
        if (val != null) html += `<div class="tp-stat"><span class="tp-stat-label">${label}</span><span class="tp-stat-value">${val}</span></div>`;
      }
      html += `</div></div>`;
      return { text: `Conta ${d.account ?? "?"}: Balance ${d.balance ?? "?"}, Equity ${d.equity ?? "?"}.`, html };
    },

    _esc(s) {
      return String(s || "").replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }
  };

  // Add CSS for trading panels
  const style = document.createElement('style');
  style.textContent = `
    .tp-section { margin: 8px 0; }
    .tp-section h3 { font-size: 13px; color: var(--gold, #d4a843); margin-bottom: 8px; }
    .tp-section h4 { font-size: 12px; color: var(--txt, #ccc); margin: 6px 0 4px; }
    .tp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; }
    .tp-card { background: var(--bg2, #141414); border: 1px solid var(--brd, #2a2a35); border-radius: 6px; padding: 8px; }
    .tp-card-head { font-size: 12px; font-weight: 600; color: var(--gold, #d4a843); margin-bottom: 4px; }
    .tp-card-body { font-size: 11px; color: var(--txt2, #999); display: flex; gap: 8px; }
    .tp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .tp-table th { text-align: left; color: var(--txt2, #999); border-bottom: 1px solid var(--brd, #2a2a35); padding: 4px 8px; }
    .tp-table td { padding: 4px 8px; color: var(--txt, #ccc); border-bottom: 1px solid rgba(42,42,53,0.3); }
    .tp-stats { display: flex; flex-wrap: wrap; gap: 12px; }
    .tp-stat { display: flex; flex-direction: column; }
    .tp-stat-label { font-size: 10px; color: var(--txt3, #666); text-transform: uppercase; }
    .tp-stat-value { font-size: 14px; font-weight: 600; color: var(--txt, #e8e8e8); }
    .tp-positive { color: #22c55e; }
    .tp-negative { color: #ef4444; }
    .tp-sub { margin-top: 8px; padding: 6px; background: rgba(0,0,0,0.2); border-radius: 4px; }
  `;
  document.head.appendChild(style);

  window.TradingPanels = TradingPanels;
})();
