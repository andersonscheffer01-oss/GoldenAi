/**
 * Golden AI Studio - Aplicação Principal
 * Tema: Ouro & Black
 */

// ============================================
// Estado da Aplicação
// ============================================

const AppState = {
    currentTab: 'chat',
    sidebarCollapsed: false,
    panelCollapsed: false,
    messages: [],
    projects: [],
    agents: [],
    memoryItems: []
};

// ============================================
// Inicialização
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    initNavigation();
    initChat();
    initQuickActions();
    initPanel();
    loadInitialData();
});

// ============================================
// Sidebar
// ============================================

function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const menuToggle = document.getElementById('menuToggle');

    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        AppState.sidebarCollapsed = !AppState.sidebarCollapsed;
    });

    menuToggle.addEventListener('click', () => {
        sidebar.classList.toggle('mobile-open');
    });

    // Fechar sidebar ao clicar fora (mobile)
    document.addEventListener('click', (e) => {
        if (window.innerWidth <= 1024 && 
            !sidebar.contains(e.target) && 
            !menuToggle.contains(e.target)) {
            sidebar.classList.remove('mobile-open');
        }
    });
}

// ============================================
// Navegação
// ============================================

function initNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const pageTitle = document.getElementById('pageTitle');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const tab = item.dataset.tab;
            switchTab(tab);
            
            // Atualizar item ativo
            navItems.forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            
            // Atualizar título
            pageTitle.textContent = item.querySelector('span').textContent;
            
            // Fechar sidebar no mobile
            if (window.innerWidth <= 1024) {
                document.getElementById('sidebar').classList.remove('mobile-open');
            }
        });
    });
}

function switchTab(tabName) {
    // Esconder todas as abas
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Mostrar aba selecionada
    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) {
        targetTab.classList.add('active');
    }
    
    AppState.currentTab = tabName;
    
    // Carregar dados da aba se necessário
    loadTabData(tabName);
}

function loadTabData(tabName) {
    switch (tabName) {
        case 'dashboard':
            updateDashboard();
            break;
        case 'projects':
            loadProjects();
            break;
        case 'agents':
            loadAgents();
            break;
        case 'memory':
            loadMemory();
            break;
    }
}

// ============================================
// Chat
// ============================================

function initChat() {
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const chatMessages = document.getElementById('chatMessages');

    // Enviar mensagem ao clicar no botão
    sendBtn.addEventListener('click', () => sendMessage());

    // Enviar mensagem ao pressionar Enter
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Auto-resize do textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });

    // Mensagem de boas-vindas
    addMessage('assistant', 'Olá! Sou o Golden AI. Como posso ajudar você hoje?');
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Adicionar mensagem do usuário
    addMessage('user', message);
    
    // Limpar input
    input.value = '';
    input.style.height = 'auto';
    
    // Simular resposta do assistente
    setTimeout(() => {
        const response = generateResponse(message);
        addMessage('assistant', response);
    }, 1000);
}

function addMessage(role, content) {
    const chatMessages = document.getElementById('chatMessages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatarIcon = role === 'user' ? 'fa-user' : 'fa-robot';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas ${avatarIcon}"></i>
        </div>
        <div class="message-content">
            ${escapeHtml(content)}
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    
    // Scroll para baixo
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Salvar no estado
    AppState.messages.push({ role, content, timestamp: new Date() });
}

function generateResponse(userMessage) {
    const lowerMessage = userMessage.toLowerCase();
    
    // Respostas baseadas em palavras-chave
    if (lowerMessage.includes('olá') || lowerMessage.includes('oi')) {
        return 'Olá! Estou aqui para ajudar. O que você precisa?';
    }
    
    if (lowerMessage.includes('status') || lowerMessage.includes('sistema')) {
        return 'O sistema está funcionando normalmente. Todos os agentes estão online e prontos para operar.';
    }
    
    if (lowerMessage.includes('mercado') || lowerMessage.includes('análise')) {
        return 'Posso ajudar com análise de mercado. Por favor, selecione um dataset CSV ou forneça os dados para análise.';
    }
    
    if (lowerMessage.includes('trading') || lowerMessage.includes('bot')) {
        return 'O bot de trading está configurado em modo demo. Deseja iniciar uma operação ou verificar as configurações?';
    }
    
    if (lowerMessage.includes('agente') || lowerMessage.includes('especialista')) {
        return 'Temos os seguintes agentes disponíveis:\n- MarketAnalyst: Análise de mercado\n- Statistician: Análise estatística\n- RiskAgent: Controle de risco\n- Programmer: Programação MQL5';
    }
    
    if (lowerMessage.includes('ajuda') || lowerMessage.includes('help')) {
        return 'Posso ajudar com:\n- Análise de mercado\n- Backtesting de estratégias\n- Programação MQL5\n- Gestão de risco\n- Consulta à memória científica\n\nO que você gostaria de fazer?';
    }
    
    return `Entendi sua mensagem: "${userMessage}". Como posso ajudar com isso?`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// Ações Rápidas
// ============================================

function initQuickActions() {
    const quickActionsBtn = document.getElementById('quickActions');
    const modal = document.getElementById('quickActionsModal');
    const closeModal = document.getElementById('closeModal');

    quickActionsBtn.addEventListener('click', () => {
        modal.classList.add('active');
    });

    closeModal.addEventListener('click', () => {
        modal.classList.remove('active');
    });

    // Fechar modal ao clicar fora
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });

    // Botões de ação rápida
    document.querySelectorAll('.quick-action-modal-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.querySelector('span').textContent;
            executeQuickAction(action);
            modal.classList.remove('active');
        });
    });
}

function executeQuickAction(action) {
    addMessage('assistant', `Executando ação: ${action}...`);
    
    // Simular execução
    setTimeout(() => {
        addMessage('assistant', `Ação "${action}" concluída com sucesso!`);
    }, 2000);
}

// ============================================
// Painel de Agentes
// ============================================

function initPanel() {
    const panelToggle = document.getElementById('panelToggle');
    const agentsPanel = document.getElementById('agentsPanel');

    panelToggle.addEventListener('click', () => {
        agentsPanel.classList.toggle('collapsed');
        AppState.panelCollapsed = !AppState.panelCollapsed;
    });
}

// ============================================
// Dashboard
// ============================================

function updateDashboard() {
    // Atualizar status bars com animação
    document.querySelectorAll('.status-fill').forEach(fill => {
        const width = fill.style.width;
        fill.style.width = '0%';
        setTimeout(() => {
            fill.style.width = width;
        }, 100);
    });
}

// ============================================
// Projetos
// ============================================

function loadProjects() {
    const projectsList = document.getElementById('projectsList');
    
    // Dados de exemplo
    const projects = [
        {
            name: 'Robo_XAUUSD_EMA_ATR_VWAP',
            description: 'Estratégia de trading para ouro usando EMA, ATR e VWAP',
            status: 'Ativo',
            lastModified: '15/08/2026'
        },
        {
            name: 'Backtest_EURUSD_RSI',
            description: 'Backtest de estratégia RSI para EURUSD',
            status: 'Concluído',
            lastModified: '12/08/2026'
        },
        {
            name: 'Analise_Mercado_Petrobras',
            description: 'Análise de mercado para ações da Petrobras',
            status: 'Em andamento',
            lastModified: '18/08/2026'
        }
    ];
    
    projectsList.innerHTML = projects.map(project => `
        <div class="project-card">
            <h4>${project.name}</h4>
            <p>${project.description}</p>
            <div class="project-meta">
                <span>${project.status}</span>
                <span>${project.lastModified}</span>
            </div>
        </div>
    `).join('');
}

// ============================================
// Agentes
// ============================================

function loadAgents() {
    const agentsGrid = document.getElementById('agentsGrid');
    
    const agents = [
        {
            name: 'MarketAnalyst',
            icon: 'fa-user-tie',
            description: 'Análise de mercado e identificação de tendências',
            status: 'Ativo'
        },
        {
            name: 'Statistician',
            icon: 'fa-user-graduate',
            description: 'Análise estatística e modelagem de dados',
            status: 'Aguardando'
        },
        {
            name: 'RiskAgent',
            icon: 'fa-user-shield',
            description: 'Controle de risco e gestão de capital',
            status: 'Aguardando'
        },
        {
            name: 'Programmer',
            icon: 'fa-user-cog',
            description: 'Programação MQL5 e desenvolvimento de EAs',
            status: 'Aguardando'
        },
        {
            name: 'PythonQuant',
            icon: 'fa-python',
            description: 'Backtesting e análise quantitativa em Python',
            status: 'Aguardando'
        },
        {
            name: 'Reviewer',
            icon: 'fa-user-check',
            description: 'Revisão e auditoria de código e estratégias',
            status: 'Aguardando'
        }
    ];
    
    agentsGrid.innerHTML = agents.map(agent => `
        <div class="agent-card-full">
            <i class="fas ${agent.icon}"></i>
            <h4>${agent.name}</h4>
            <p>${agent.description}</p>
            <span class="agent-status ${agent.status === 'Ativo' ? 'active' : 'idle'}">
                ${agent.status}
            </span>
        </div>
    `).join('');
}

// ============================================
// Memória
// ============================================

function loadMemory() {
    const memoryList = document.getElementById('memoryList');
    
    const memoryItems = [
        {
            topic: 'Estratégia EMA crossover',
            statement: 'Cruzamento de EMA 20/50 mostra consistência em timeframes H1 e H4',
            evidenceLevel: 'TESTED',
            source: 'Backtest 2024'
        },
        {
            topic: 'Gestão de risco',
            statement: 'Stop loss deve ser no máximo 2% do capital por operação',
            evidenceLevel: 'VALIDATED',
            source: 'Regras gerais'
        },
        {
            topic: 'Indicador VWAP',
            statement: 'VWAP funciona melhor em mercados com alta liquidez',
            evidenceLevel: 'SOURCE_CLAIM',
            source: 'Artigo técnico'
        }
    ];
    
    memoryList.innerHTML = memoryItems.map(item => `
        <div class="memory-item">
            <h4>${item.topic}</h4>
            <p>${item.statement}</p>
            <div class="memory-meta">
                <span class="evidence-level ${item.evidenceLevel.toLowerCase()}">${item.evidenceLevel}</span>
                <span>${item.source}</span>
            </div>
        </div>
    `).join('');
}

// ============================================
// Dados Iniciais
// ============================================

function loadInitialData() {
    // Carregar dados do backend se disponível
    fetchSystemStatus();
}

function fetchSystemStatus() {
    // Simular busca de status do sistema
    // Em produção, isso faria uma chamada API
    console.log('Golden AI Studio iniciado');
}

// ============================================
// Notificações
// ============================================

function showNotification(message, type = 'info') {
    // Criar elemento de notificação
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;
    
    // Estilo da notificação
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: var(--dark-card);
        border: 1px solid var(--${type === 'success' ? 'success' : type === 'error' ? 'error' : 'info'});
        border-radius: 8px;
        padding: 15px 20px;
        display: flex;
        align-items: center;
        gap: 10px;
        z-index: 1001;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    // Remover após 3 segundos
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============================================
// Utilitários
// ============================================

function formatNumber(num) {
    return new Intl.NumberFormat('pt-BR').format(num);
}

function formatDate(date) {
    return new Intl.DateTimeFormat('pt-BR').format(date);
}

// ============================================
// Exportar funções para uso externo
// ============================================

window.GoldenAIStudio = {
    sendMessage,
    addMessage,
    switchTab,
    executeQuickAction,
    showNotification
};
