(function () {
  let statusData = null;
  let data = { connections: [], accounts: [], bills: [], transactions: [] };
  let syncNotice = '';
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
  const money = (value, currency = 'BRL') => new Intl.NumberFormat('pt-BR', { style: 'currency', currency }).format((value || 0) / 100);
  const date = value => value ? new Date(value).toLocaleDateString('pt-BR') : 'Não informado';

  function shell() {
    const root = document.getElementById('view-open-finance');
    root.innerHTML = `<div class="page-heading"><div><p class="eyebrow">Meu Pluggy</p><h1>Open Finance</h1><p>Suas contas pessoais em um painel somente leitura.</p></div><div class="of-toolbar"><button class="secondary-btn" id="ofRefresh">Atualizar painel</button><button class="secondary-btn" id="ofSyncAll">Sincronizar todos</button><button class="primary-btn" id="ofConnect">Como adicionar bancos</button></div></div><div id="ofBody"><div class="of-empty">Carregando Open Finance...</div></div>`;
    document.getElementById('ofConnect').onclick = chooseBank;
    // Refreshing this screen must also request fresh provider data.
    document.getElementById('ofRefresh').onclick = syncAll;
    document.getElementById('ofSyncAll').onclick = syncAll;
  }

  function render() {
    const body = document.getElementById('ofBody');
    const configured = statusData?.configured;
    const active = (statusData?.connections || []).filter(item => item.status !== 'disconnected');
    body.innerHTML = `${configured ? '<div class="of-status">Modo pessoal e somente leitura. Pagamentos, Pix e transferências estão desativados.</div>' : '<div class="of-status warning">Configure PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET no arquivo .env do servidor.</div>'}${syncNotice ? `<div class="of-status warning">${esc(syncNotice)}</div>` : ''}
      <section class="panel"><div class="panel-head"><div><h2>Conexões</h2><p>${active.length} Item(ns) registrado(s) para este usuário. Cada banco/Item é mantido separadamente; a Pluggy pode atualizar o MeuPluggy em ciclo diário.</p></div><button class="secondary-btn" id="ofDiagnostic">Diagnóstico dos Items</button></div>${active.length ? active.map(conn => `<div class="of-connection"><div><strong>${esc(conn.institution_name || 'Instituição')}</strong><small>Item local #${conn.id} · ${conn.status === 'connected' ? 'Conectada' : 'Processando'} · última sincronização ${conn.last_sync_at ? date(conn.last_sync_at) : 'ainda não realizada'}</small></div><div class="of-toolbar"><button class="secondary-btn" data-sync="${conn.id}">Sincronizar Item</button><button class="secondary-btn danger-button" data-disconnect="${conn.id}">Desconectar</button></div></div>`).join('') : '<div class="of-empty">Nenhum Item registrado. Use “Adicionar banco” para vincular uma instituição nesta aplicação.</div>'}</section>
      <section class="panel"><div class="panel-head"><div><h2>Contas e cartões</h2><p>Saldos informados pelas instituições conectadas, separados por produto.</p></div></div><div class="of-account-grid">${data.accounts.length ? data.accounts.map(account => `<article class="of-account"><h3>${esc(account.institution_name || 'Instituição')} · ${esc(account.name)}</h3><p>${esc(account.type || 'CONTA')} ${account.subtype ? '· ' + esc(account.subtype) : ''} · Item ${esc(account.item_id || 'não informado')}</p><strong>${money(account.current_balance_cents, account.currency)}</strong>${account.credit_limit_cents != null ? `<p>Limite ${money(account.credit_limit_cents, account.currency)}</p>` : ''}</article>`).join('') : '<div class="of-empty">Sincronize uma conexão para visualizar contas e cartões.</div>'}</div></section>
      <section class="panel"><div class="panel-head"><div><h2>Faturas</h2><p>Disponíveis conforme cobertura de cada instituição.</p></div></div>${data.bills.length ? `<div class="of-table-wrap"><table class="of-table"><thead><tr><th>Instituição</th><th>Cartão</th><th>Vencimento</th><th>Status</th><th>Total</th><th>Mínimo</th></tr></thead><tbody>${data.bills.map(bill => `<tr><td>${esc(bill.institution_name || '—')}</td><td>${esc(bill.account_name || bill.account_external_id || '—')}</td><td>${date(bill.due_date)}</td><td>${esc(bill.status || '—')}</td><td>${money(bill.total_cents)}</td><td>${money(bill.minimum_cents)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="of-empty">Nenhuma fatura disponível.</div>'}</section>
      <section class="panel"><div class="panel-head"><div><h2>Transações</h2><p>Selecione movimentações e revise antes de importar.</p></div><button class="primary-btn" id="ofPrepare">Revisar importação</button></div>${data.transactions.length ? `<div class="of-table-wrap"><table class="of-table"><thead><tr><th></th><th>Data</th><th>Descrição</th><th>Categoria Pluggy</th><th>Status</th><th class="amount">Valor</th></tr></thead><tbody>${data.transactions.map(tx => `<tr><td>${tx.import_status === 'available' ? `<input class="of-check" type="checkbox" value="${tx.id}">` : esc(tx.import_status === 'imported' ? 'Importada' : 'Pendente')}</td><td>${date(tx.occurred_at)}</td><td>${esc(tx.description)}</td><td>${esc(tx.provider_category || 'Não informada')}</td><td>${esc(tx.status || '—')}</td><td class="amount ${tx.flow_type === 'expense' ? 'expense-text' : 'income-text'}">${tx.flow_type === 'expense' ? '-' : '+'}${money(tx.amount_cents, tx.currency)}</td></tr>`).join('')}</tbody></table></div>` : '<div class="of-empty">Nenhuma transação sincronizada.</div>'}</section>`;
    body.querySelectorAll('[data-sync]').forEach(button => button.onclick = () => sync(button.dataset.sync));
    body.querySelectorAll('[data-disconnect]').forEach(button => button.onclick = () => disconnect(button.dataset.disconnect));
    document.getElementById('ofPrepare').onclick = prepareImport;
    document.getElementById('ofDiagnostic').onclick = diagnostic;
  }

  async function load() {
    try {
      [statusData, data] = await Promise.all([JarvisAPI.request('/api/open-finance/status'), JarvisAPI.request('/api/open-finance/data')]);
      render();
    } catch (error) { document.getElementById('ofBody').innerHTML = `<div class="of-status warning">${esc(error.message)}</div>`; }
  }

  function chooseBank() {
    const modal = document.createElement('div'); modal.className = 'modal-backdrop';
    modal.innerHTML = `<section class="form-modal"><div class="panel-head"><div><h2>Adicionar banco</h2><p>O Widget Pluggy registra cada instituição como um Item separado.</p></div><button class="icon-only" data-close>×</button></div><div class="of-status">Escolha a instituição no Widget e conclua a autorização somente leitura. O Jarvis não solicita nem armazena sua senha bancária.</div><p>Items existentes apenas no portal MeuPluggy não podem ser descobertos pela API. Para que Inter ou BV apareçam nesta aplicação, vincule-os pelo botão abaixo.</p><div class="form-actions"><button type="button" class="secondary-btn" data-understood>Fechar</button><button type="button" class="primary-btn" data-connect>Adicionar no Widget</button></div></section>`;
    document.body.appendChild(modal); modal.querySelector('[data-close]').onclick = () => modal.remove();
    modal.querySelector('[data-understood]').onclick = () => modal.remove(); modal.querySelector('[data-connect]').onclick = () => { modal.remove(); connect(); };
  }

  async function connect(selectedConnectorId = null) {
    if (typeof PluggyConnect !== 'function') return alert('O Widget do Meu Pluggy não pôde ser carregado. Verifique a internet.');
    try {
      const session = await JarvisAPI.request('/api/open-finance/connect-token', { method: 'POST' });
      const options = { connectToken: session.connect_token, includeSandbox: Boolean(session.include_sandbox), connectorTypes: ['PERSONAL_BANK'], onSuccess: async result => {
        const itemId = result.item?.id || result.itemId || result.id;
        if (!itemId) return alert('Conexão concluída, mas o identificador não foi recebido.');
        const connection = await JarvisAPI.request('/api/open-finance/connections/finish', { method: 'POST', json: { item_id: itemId } });
        syncNotice = `Item registrado: ${connection.institution_name || 'Instituição'} · ${connection.item_id_masked}. Sincronizando dados...`;
        await load();
        const summary = await JarvisAPI.request(`/api/open-finance/connections/${connection.id}/sync`, { method: 'POST', timeout: 120000 });
        syncNotice = `${connection.institution_name || 'Instituição'} · Item ${connection.item_id_masked}: ${summary.provider_accounts || 0} produtos, ${summary.transactions_received || 0} transações e ${summary.bills_received || 0} faturas. Status: sincronizado.`;
        await load(); await JarvisDashboard.renderFinance();
      }, onError: error => { const item = error?.data?.item || error?.item || {}; const detail = item.statusDetail || error?.data?.statusDetail || {}; const code = safeCode(detail.code || detail.name || item.status || error?.code || 'CONNECTOR_ACCESS'); alert(`A Pluggy não autorizou esta conexão (${code}). Nenhuma credencial bancária foi armazenada pelo Jarvis. Verifique se a aplicação Pluggy está habilitada para conexões reais e não está em Sandbox.`); }
      };
      if (selectedConnectorId) options.selectedConnectorId = selectedConnectorId;
      new PluggyConnect(options).init();
    } catch (error) { alert(error.message); }
  }

  function safeCode(value) { return String(value || 'ACTION_REQUIRED').replace(/[^A-Z0-9_\-]/gi, '').slice(0, 80); }
  async function openUpdate(id, technicalCode) {
    if (typeof PluggyConnect !== 'function') return alert(`Ação necessária (${safeCode(technicalCode)}). O Widget não pôde ser carregado.`);
    try {
      const session = await JarvisAPI.request(`/api/open-finance/connections/${id}/update-token`, { method: 'POST' });
      new PluggyConnect({ connectToken: session.connect_token, updateItem: session.item_id, includeSandbox: Boolean(session.include_sandbox), connectorTypes: ['PERSONAL_BANK'], onSuccess: async result => {
        const itemId = result.item?.id || result.itemId || result.id || session.item_id;
        await JarvisAPI.request('/api/open-finance/connections/finish', { method: 'POST', json: { item_id: itemId } });
        await sync(id);
      }, onError: error => {
        const item = error?.data?.item || {}; const detail = item.statusDetail || {};
        alert(`Não foi possível concluir a autorização (${safeCode(detail.code || item.status || technicalCode)}).`);
      } }).init();
    } catch (error) { alert(`Não foi possível abrir a autorização (${safeCode(error.code)}).`); }
  }
  async function sync(id) {
    const button = document.querySelector(`[data-sync="${id}"]`);
    if (button?.disabled) return;
    const originalLabel = button?.textContent;
    if (button) { button.disabled = true; button.textContent = 'Buscando na Pluggy...'; }
    try {
      const result = await JarvisAPI.request(`/api/open-finance/connections/${id}/sync`, { method: 'POST', timeout: 120000 });
      const names = (result.provider_account_names || []).join(', ');
      syncNotice = `Busca concluída. A Pluggy disponibilizou ${result.provider_accounts || 0} produtos: ${names || 'nenhum'}. Foram recebidas ${result.transactions_received || 0} transações e ${result.bills_received || 0} faturas. Se Inter e BV não aparecem aqui, eles ainda não foram entregues pela API ao Item MeuPluggy.`;
      await load(); await JarvisDashboard.renderFinance();
    }
    catch (error) {
      if (error.requires_user_action) return openUpdate(id, error.code);
      alert(`Falha na sincronização (${safeCode(error.code || 'SYNC_ERROR')}).`);
    }
    finally { if (button?.isConnected) { button.disabled = false; button.textContent = originalLabel; } }
  }
  async function syncAll() {
    const button = document.getElementById('ofSyncAll'); if (!button || button.disabled) return;
    button.disabled = true; const label = button.textContent; button.textContent = 'Sincronizando Items...';
    try { const result = await JarvisAPI.request('/api/open-finance/connections/sync-all', { method: 'POST', timeout: 180000 }); const errors = (result.results || []).filter(x => x.error); syncNotice = `Processados ${result.items_processed || 0} de ${result.items_total || 0} Item(ns). ${errors.length ? `${errors.length} exigem atenção no Widget.` : 'Todos processados.'}`; await load(); await JarvisDashboard.renderFinance(); }
    catch (error) { syncNotice = `Falha coletiva (${safeCode(error.code || 'SYNC_ALL_ERROR')}).`; await load(); }
    finally { if (button.isConnected) { button.disabled = false; button.textContent = label; } }
  }
  async function diagnostic() {
    try { const result = await JarvisAPI.request('/api/open-finance/diagnostico'); const lines = (result.items || []).map(item => `${item.institution || 'Instituição'} · status ${item.provider_status || item.status} · contas ${item.accounts} · cartões ${item.cards} · transações ${item.transactions} · faturas ${item.bills} · última atualização ${item.last_sync_at ? date(item.last_sync_at) : 'não realizada'}${item.error ? ` · erro ${item.error}` : ''}`); alert(`Items registrados: ${result.items_total}\n\n${lines.join('\n') || 'Nenhum Item registrado.'}\n\nItaú: ${result.instituicoes_esperadas?.['Itaú'] ? 'encontrado' : 'não encontrado'} · Inter: ${result.instituicoes_esperadas?.Inter ? 'encontrado' : 'não encontrado'} · BV: ${result.instituicoes_esperadas?.BV ? 'encontrado' : 'não encontrado'}`); }
    catch (error) { alert(`Diagnóstico indisponível (${safeCode(error.code || 'DIAGNOSTIC_ERROR')}).`); }
  }
  async function disconnect(id) { if (!confirm('Revogar o consentimento e desconectar esta instituição?')) return; try { await JarvisAPI.request(`/api/open-finance/connections/${id}`, { method: 'DELETE' }); await load(); } catch (error) { alert(error.message); } }

  async function prepareImport() {
    const ids = [...document.querySelectorAll('.of-check:checked')].map(input => Number(input.value));
    if (!ids.length) return alert('Selecione ao menos uma transação.');
    const categories = await JarvisAPI.request('/api/financas/categorias');
    const expenses = categories.filter(c => c.tipo === 'despesa'); const incomes = categories.filter(c => c.tipo === 'receita');
    const modal = document.createElement('div'); modal.className = 'modal-backdrop';
    modal.innerHTML = `<section class="form-modal"><div class="panel-head"><div><h2>Revisar importação</h2><p>Nada será salvo antes da sua confirmação final.</p></div><button class="icon-only" data-close>×</button></div><form class="professional-form"><label>Categoria das despesas<select name="expense_category_id"><option value="">Selecione</option>${expenses.map(c => `<option value="${c.id}">${esc(c.nome)}</option>`).join('')}</select></label><label>Categoria das receitas<select name="income_category_id"><option value="">Selecione</option>${incomes.map(c => `<option value="${c.id}">${esc(c.nome)}</option>`).join('')}</select></label><p class="form-error"></p><div class="form-actions"><button type="button" class="secondary-btn" data-cancel>Cancelar</button><button class="primary-btn">Preparar ${ids.length} transações</button></div></form></section>`;
    document.body.appendChild(modal); const close = () => modal.remove(); modal.querySelector('[data-close]').onclick = close; modal.querySelector('[data-cancel]').onclick = close;
    modal.querySelector('form').onsubmit = async event => { event.preventDefault(); const form = new FormData(event.target); try { const batch = await JarvisAPI.request('/api/open-finance/imports/prepare', { method: 'POST', json: { transaction_ids: ids, expense_category_id: Number(form.get('expense_category_id')) || null, income_category_id: Number(form.get('income_category_id')) || null } }); if (!confirm(`${batch.summary}. Confirmar e criar os lançamentos agora?`)) { await JarvisAPI.request(`/api/open-finance/imports/${batch.id}/cancel`, { method: 'POST' }); close(); return; } await JarvisAPI.request(`/api/open-finance/imports/${batch.id}/confirm`, { method: 'POST' }); close(); await load(); await JarvisDashboard.renderFinance(); alert('Transações importadas com sucesso.'); } catch (error) { modal.querySelector('.form-error').textContent = error.message; } };
  }

  async function init() { shell(); await load(); }
  window.JarvisOpenFinance = { init, load };
})();
