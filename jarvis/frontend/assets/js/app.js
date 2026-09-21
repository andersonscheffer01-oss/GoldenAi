(async function () {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }

  if (!JarvisAuth.requireLogin()) return;

  const dot = document.getElementById('apiDot');
  const status = document.getElementById('apiStatus');
  let currentUser = JarvisAPI.user();
  let apiOk = false;

  try {
    const health = await JarvisAPI.request('/api/health');
    apiOk = health.status === 'ok';
    dot.classList.toggle('ok', apiOk);
    status.textContent = apiOk ? 'API online' : 'API indisponivel';
    currentUser = await JarvisAuth.me();
    document.getElementById('userName').textContent = currentUser.nome || 'Usuário';
    document.getElementById('userInitial').textContent = (currentUser.nome || 'U').slice(0, 1).toUpperCase();
  } catch (err) {
    status.textContent = err.message || 'API indisponivel';
  }

  await JarvisChat.initChat();
  await JarvisDashboard.renderFinance();
  await JarvisDashboard.renderAlerts();
  await JarvisOpenFinance.init();
  JarvisDashboard.renderSettings(currentUser, apiOk);

  document.querySelectorAll('[data-finance-section]').forEach(button => button.addEventListener('click', () => JarvisDashboard.showFinanceSection(button.dataset.financeSection)));
  document.querySelectorAll('[data-target-view]').forEach(button => button.addEventListener('click', () => JarvisDashboard.showView(button.dataset.targetView)));
})();
