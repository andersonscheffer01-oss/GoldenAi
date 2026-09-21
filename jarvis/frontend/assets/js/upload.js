(function () {
  const allowed = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];
  let currentAnalysis = null;

  function validate(file) {
    if (!file) throw new Error('Selecione um arquivo.');
    if (!allowed.includes(file.type)) throw new Error('Tipo nao permitido. Use JPG, PNG, WEBP ou PDF.');
    if (file.size > 10 * 1024 * 1024) throw new Error('Arquivo acima do limite de 10 MB.');
  }

  async function upload(file) {
    validate(file);
    const form = new FormData();
    form.append('file', file);
    const data = await JarvisAPI.request('/api/uploads', { method: 'POST', body: form, timeout: 60000 });
    await refreshList();
    return data;
  }

  async function analyze(fileId) {
    const button = document.querySelector('[data-analyze="' + fileId + '"]');
    if (button) { button.disabled = true; button.textContent = 'Analisando...'; }
    try {
      currentAnalysis = await JarvisAPI.request('/api/comprovantes/' + fileId + '/analisar', { method: 'POST', timeout: 150000 });
      await showAnalysis(currentAnalysis);
      await refreshList();
    } catch (error) {
      alert(error.message || 'Nao foi possivel analisar o comprovante.');
    } finally {
      if (button) { button.disabled = false; button.textContent = 'Analisar comprovante'; }
    }
  }

  async function showAnalysis(analysis) {
    const old = document.getElementById('receiptModal');
    if (old) old.remove();
    const data = analysis.dados_extraidos || {};
    const modal = document.createElement('div');
    modal.id = 'receiptModal'; modal.className = 'modal-backdrop';
    modal.innerHTML = `<section class="receipt-modal card" role="dialog" aria-modal="true">
      <div class="modal-header"><div><h2>Conferir comprovante</h2><div class="upload-meta">Status: ${escapeHtml(statusLabel(analysis.status))}</div></div><button class="icon-btn" data-close>Fechar</button></div>
      <div class="receipt-preview"><img id="receiptImage" alt="Comprovante enviado"><div id="receiptFileNote" class="upload-meta">Carregando visualizacao...</div></div>
      <div class="receipt-grid">
        ${field('Tipo do documento', 'tipo_documento', data.tipo_documento || 'documento_desconhecido')}
        ${field('Estabelecimento', 'estabelecimento', data.estabelecimento)}
        ${field('CNPJ', 'cnpj', data.cnpj)}
        ${field('Data', 'data', data.data, 'date')}
        ${field('Hora', 'hora', data.hora)}
        ${field('Valor total', 'valor_total', data.valor_total, 'number', data.confianca?.valor_total)}
        ${field('Forma de pagamento', 'forma_pagamento', data.forma_pagamento)}
        ${field('Banco', 'banco', data.banco)}
        ${field('Ultimos 4 digitos', 'ultimos_quatro_digitos', data.ultimos_quatro_digitos, 'text', null, 4)}
        ${field('Observacoes', 'observacoes', data.observacoes)}
      </div>
      <div class="confidence-note ${analysis.confianca_geral < .9 ? 'low-confidence' : ''}">Confianca geral: ${Math.round((analysis.confianca_geral || 0) * 100)}%. Revise os campos destacados antes de confirmar.</div>
      ${analysis.erro_mensagem ? `<div class="error-text">${escapeHtml(analysis.erro_mensagem)}</div>` : ''}
      <div class="modal-actions"><button class="action-btn" data-retry>Reanalisar</button><button class="action-btn" data-cancel>Cancelar</button><button class="action-btn primary" data-confirm>Confirmar</button></div>
    </section>`;
    document.body.appendChild(modal);
    modal.querySelector('[data-close]').onclick = () => modal.remove();
    try {
      const response = await fetch('/api/uploads/' + analysis.arquivo_id + '/content', { headers: { Authorization: 'Bearer ' + JarvisAPI.token() } });
      if (response.ok && response.headers.get('content-type')?.startsWith('image/')) {
        document.getElementById('receiptImage').src = URL.createObjectURL(await response.blob());
        document.getElementById('receiptFileNote').textContent = 'Imagem pronta para conferencia.';
      } else document.getElementById('receiptFileNote').textContent = 'PDF recebido. A visualizacao fica disponivel no arquivo enviado.';
    } catch (_) { document.getElementById('receiptFileNote').textContent = 'Visualizacao indisponivel.'; }
    modal.querySelector('[data-cancel]').onclick = async () => { await analysisAction('/api/analises/' + analysis.id + '/cancelar', {}, modal); };
    modal.querySelector('[data-retry]').onclick = async () => { modal.remove(); await analyze(analysis.arquivo_id); };
    modal.querySelector('[data-confirm]').onclick = async () => {
      const edited = { ...data };
      modal.querySelectorAll('[data-field]').forEach(input => { edited[input.dataset.field] = input.value || null; });
      if (edited.valor_total !== null) edited.valor_total = Number(edited.valor_total);
      await analysisAction('/api/analises/' + analysis.id + '/confirmar', { dados: edited }, modal);
    };
  }

  async function analysisAction(path, json, modal) {
    try {
      currentAnalysis = await JarvisAPI.request(path, { method: 'POST', json });
      modal.remove();
      await refreshList();
      if (path.includes('/confirmar') && confirm('Deseja criar este lancamento financeiro com os dados confirmados?')) {
        const created = await JarvisAPI.request('/api/analises/' + currentAnalysis.id + '/gerar-lancamento', { method: 'POST' });
        alert(created.mensagem || 'Lancamento criado. Ele ja aparece na dashboard financeira.');
      }
    }
    catch (error) { alert(error.message || 'Nao foi possivel atualizar a analise.'); }
  }

  function field(label, name, value, type = 'text', confidence = null, maxLength = '') {
    const low = confidence !== null && confidence < .7 ? ' low-confidence' : '';
    return `<label class="receipt-field${low}">${label}<input data-field="${name}" type="${type}" value="${escapeHtml(value ?? '')}" ${maxLength ? 'maxlength="' + maxLength + '"' : ''}></label>`;
  }

  function statusLabel(status) {
    return ({ aguardando: 'Aguardando analise', processando: 'Analisando', concluida: 'Analise concluida', requer_confirmacao: 'Revisar informacoes', confirmada: 'Confirmada', cancelada: 'Cancelada', erro: 'Erro' }[status] || status);
  }

  async function refreshList() {
    const list = document.getElementById('uploadList');
    if (!list) return;
    try {
      const files = await JarvisAPI.request('/api/uploads');
      list.replaceChildren();
      if (!files.length) { list.textContent = 'Nenhum arquivo enviado ainda.'; return; }
      files.forEach(file => list.appendChild(renderItem(file)));
    } catch (err) { list.textContent = err.message; list.className = 'error-text'; }
  }

  function renderItem(file) {
    const item = document.createElement('div'); item.className = 'card upload-item';
    const info = document.createElement('div');
    info.innerHTML = `<div class="upload-name">${escapeHtml(file.nome_original)}</div><div class="upload-meta">${escapeHtml(file.mime_type)} - ${JarvisChat.formatBytes(file.tamanho_bytes)} - ${escapeHtml(file.status)}</div>`;
    const actions = document.createElement('div');
    const button = document.createElement('button'); button.className = 'icon-btn'; button.textContent = 'Analisar comprovante'; button.dataset.analyze = file.id; button.onclick = () => analyze(file.id);
    actions.appendChild(button); item.append(info, actions); return item;
  }

  function renderUploadArea() {
    const el = document.getElementById('uploadArea'); if (!el) return;
    el.innerHTML = `<div class="upload-actions"><button class="action-btn" id="takePhoto">Tirar foto</button><button class="action-btn" id="pickGallery">Escolher da galeria</button><button class="action-btn" id="pickDocument">Enviar documento</button></div><div id="uploadPreviewBox" class="preview hidden"></div><div class="progress"><span id="uploadProgress"></span></div><div id="uploadMessage" class="success-text"></div><div id="uploadList" class="upload-list"></div><input id="takePhotoInput" class="hidden-input" type="file" accept="image/*" capture="environment"><input id="galleryInput" class="hidden-input" type="file" accept="image/*"><input id="documentInput" class="hidden-input" type="file" accept="image/jpeg,image/png,image/webp,application/pdf">`;
    bindInput('takePhoto', 'takePhotoInput'); bindInput('pickGallery', 'galleryInput'); bindInput('pickDocument', 'documentInput'); refreshList();
  }

  function bindInput(buttonId, inputId) {
    document.getElementById(buttonId).onclick = () => document.getElementById(inputId).click();
    document.getElementById(inputId).onchange = async event => {
      const file = event.target.files[0]; const message = document.getElementById('uploadMessage');
      try { validate(file); const result = await upload(file); message.className = 'success-text'; message.textContent = result.mensagem || 'Arquivo recebido.'; }
      catch (err) { message.className = 'error-text'; message.textContent = err.message; }
      finally { event.target.value = ''; }
    };
  }

  function escapeHtml(value) { return String(value || '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[ch])); }
  window.JarvisUpload = { upload, refreshList, renderUploadArea };
})();
