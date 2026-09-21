(function () {
  let pendingFile = null;
  let currentConversationId = null;
  let lastFailedText = '';

  function addMessage(role, text, options = {}) {
    const list = document.getElementById('messages');
    if (!list) return null;
    const bubble = document.createElement('div');
    bubble.className = 'message ' + role;
    bubble.textContent = text;
    if (options.id) bubble.dataset.messageId = options.id;
    list.appendChild(bubble);
    list.scrollTop = list.scrollHeight;
    return bubble;
  }

  function clearMessages() {
    const list = document.getElementById('messages');
    if (list) list.replaceChildren();
  }

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
    return value.toFixed(unit ? 1 : 0) + ' ' + units[unit];
  }

  function setPreview(file) {
    pendingFile = file || null;
    const preview = document.getElementById('chatPreview');
    if (!preview) return;
    if (!file) { preview.classList.add('hidden'); preview.replaceChildren(); return; }
    preview.classList.remove('hidden');
    preview.replaceChildren();
    const label = document.createElement('span');
    label.textContent = file.name + ' - ' + formatBytes(file.size);
    const remove = document.createElement('button');
    remove.className = 'icon-btn'; remove.textContent = 'Remover';
    remove.onclick = () => setPreview(null);
    preview.append(label, remove);
  }

  async function refreshConversations() {
    const conversations = await JarvisAPI.request('/api/chat/conversas');
    const list = document.getElementById('conversationList');
    list.replaceChildren();
    conversations.forEach(conversation => {
      const button = document.createElement('button');
      button.className = 'conversation-item' + (conversation.id === currentConversationId ? ' active' : '');
      button.textContent = conversation.titulo;
      button.title = conversation.titulo;
      button.onclick = () => openConversation(conversation.id);
      list.appendChild(button);
    });
    document.getElementById('conversationStatus').textContent = conversations.length + ' conversa' + (conversations.length === 1 ? '' : 's');
  }

  async function openConversation(id) {
    const conversation = await JarvisAPI.request('/api/chat/conversas/' + id);
    currentConversationId = conversation.id;
    clearMessages();
    conversation.mensagens.forEach(message => addMessage(message.role === 'usuario' ? 'user' : 'jarvis', message.content, { id: message.id }));
    await refreshConversations();
  }

  async function newConversation() {
    const conversation = await JarvisAPI.request('/api/chat/conversas', { method: 'POST', json: { titulo: 'Nova conversa' } });
    currentConversationId = conversation.id;
    clearMessages();
    addMessage('jarvis', 'Ola, Anderson. Como posso ajudar?');
    await refreshConversations();
  }

  function setSending(sending) {
    document.getElementById('sendButton').disabled = sending;
    document.getElementById('chatInput').disabled = sending;
    document.getElementById('sendButton').textContent = sending ? '...' : 'Enviar';
  }

  async function sendMessage(textOverride = '') {
    const input = document.getElementById('chatInput');
    const text = (textOverride || input.value || '').trim();
    if ((!text && !pendingFile) || document.getElementById('sendButton').disabled) return;
    setSending(true);
    lastFailedText = text;
    if (text) addMessage('user', text);
    input.value = '';
    try {
      if (pendingFile) {
        addMessage('user', 'Arquivo recebido: ' + pendingFile.name);
        await JarvisUpload.upload(pendingFile);
        addMessage('jarvis', 'Arquivo recebido. A analise inteligente sera ativada na proxima etapa.');
        setPreview(null);
      }
      if (text) {
        const thinking = addMessage('jarvis', 'Jarvis esta pensando...');
        const command = await JarvisAPI.request('/api/jarvis/comando', { method: 'POST', json: { content: text } });
        if (command.status !== 'fallback') {
          thinking.remove();
          addMessage('jarvis', command.message || command.resumo || 'Comando processado.');
          if (command.status === 'aguardando_confirmacao' && command.acao_id) {
            const actions = document.createElement('div');
            actions.innerHTML = '<button class="action-btn primary">Confirmar</button><button class="action-btn">Cancelar</button>';
            actions.children[0].onclick = async () => { const result = await JarvisAPI.request('/api/jarvis/acoes/' + command.acao_id + '/confirmar', { method: 'POST' }); addMessage('jarvis', result.message); actions.remove(); };
            actions.children[1].onclick = async () => { const result = await JarvisAPI.request('/api/jarvis/acoes/' + command.acao_id + '/cancelar', { method: 'POST' }); addMessage('jarvis', result.message); actions.remove(); };
            document.getElementById('messages').appendChild(actions);
          }
          return;
        }
        const result = await JarvisAPI.request('/api/chat/mensagem', { method: 'POST', json: { conversation_id: currentConversationId, content: text } });
        thinking.remove();
        currentConversationId = result.conversation_id;
        addMessage('jarvis', result.assistant_message.content, { id: result.assistant_message.id });
        await refreshConversations();
      }
    } catch (error) {
      addMessage('jarvis', error.message || 'Nao foi possivel obter uma resposta.');
      if (lastFailedText) {
        const retry = document.createElement('button');
        retry.className = 'action-btn'; retry.textContent = 'Tentar novamente';
        retry.onclick = () => { retry.remove(); sendMessage(lastFailedText); };
        document.getElementById('messages').appendChild(retry);
      }
    } finally {
      setSending(false);
      input.focus();
    }
  }

  async function initChat() {
    document.getElementById('sendButton').onclick = () => sendMessage();
    document.getElementById('newConversationButton').onclick = newConversation;
    document.getElementById('chatInput').addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
    });
    document.getElementById('cameraButton').onclick = () => document.getElementById('chatImageInput').click();
    document.getElementById('attachButton').onclick = () => document.getElementById('chatFileInput').click();
    document.getElementById('chatImageInput').onchange = event => setPreview(event.target.files[0]);
    document.getElementById('chatFileInput').onchange = event => setPreview(event.target.files[0]);
    document.getElementById('micButton').onclick = () => addMessage('jarvis', 'A funcao de voz sera conectada em uma etapa futura.');
    try {
      const conversations = await JarvisAPI.request('/api/chat/conversas');
      if (conversations.length) await openConversation(conversations[0].id);
      else await newConversation();
    } catch (error) {
      addMessage('jarvis', error.message || 'Nao foi possivel carregar suas conversas.');
    }
  }

  window.JarvisChat = { initChat, addMessage, formatBytes };
})();
