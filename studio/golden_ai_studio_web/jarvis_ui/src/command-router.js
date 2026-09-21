/**
 * Command Router — Replaces brain.js direct command execution
 * 
 * ALL commands route through Gateway → JarvisService → ToolRegistry → SecurityManager
 * No direct OS actions from browser. No parallel intelligence.
 * 
 * Browser-side only: clock, theme, state, UI helpers
 * Everything else: Gateway.sendCommand()
 */
(function() {
  'use strict';

  const CommandRouter = {
    // Local commands that don't need Gateway (purely UI)
    LOCAL_COMMANDS: {
      'tema': true, 'theme': true, 'trocar tema': true,
      'hora': true, 'clock': true, 'relogio': true,
      'data': true, 'date': true,
      'limpar': true, 'clear': true, 'limpar historico': true,
      'sombra': true, 'shadow': true,
      'tela cheia': true, 'fullscreen': true,
      'ajuda': true, 'help': true,
    },

    /**
     * Route a command. Returns { type: 'local'|'gateway'|'error', result: any }
     */
    async route(input) {
      if (!input || typeof input !== 'string') {
        return { type: 'error', result: 'Comando vazio' };
      }

      const normalized = input.trim().toLowerCase();

      // Check for calculator: "calcular X", "calc X", "math X"
      const calcMatch = normalized.match(/^(?:calcular?|calc|math|matematica)\s+(.+)$/i);
      if (calcMatch) {
        return this._handleCalc(calcMatch[1]);
      }

      // Check local commands
      if (this.LOCAL_COMMANDS[normalized]) {
        return this._handleLocal(normalized);
      }

      // Everything else goes to Gateway
      return this._handleGateway(input);
    },

    _handleCalc(expr) {
      try {
        if (!window.MathParser) {
          return { type: 'error', result: 'Parser matemático não disponível' };
        }
        const result = window.MathParser.evaluate(expr);
        return { type: 'local', result: String(result) };
      } catch (err) {
        return { type: 'error', result: 'Erro ao calcular: ' + err.message };
      }
    },

    _handleLocal(command) {
      switch (command) {
        case 'hora': case 'clock': case 'relogio':
          return { type: 'local', result: new Date().toLocaleTimeString('pt-BR') };
        case 'data': case 'date':
          return { type: 'local', result: new Date().toLocaleDateString('pt-BR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) };
        case 'ajuda': case 'help':
          return { type: 'local', result: 'Comandos disponíveis: tema, hora, data, limpar, sombra, tela cheia, calcular <expressão>. Outros comandos são encaminhados ao Gateway.' };
        default:
          return { type: 'local', result: 'Comando local executado' };
      }
    },

    async _handleGateway(command) {
      if (!window.Gateway || !window.Gateway.isAuthenticated) {
        return { type: 'error', result: 'Gateway não conectado. Conecte-se primeiro.' };
      }
      try {
        const result = await window.Gateway.sendCommand(command);
        return { type: 'gateway', result: result };
      } catch (err) {
        return { type: 'error', result: 'Erro do Gateway: ' + err.message };
      }
    }
  };

  window.CommandRouter = CommandRouter;
})();
