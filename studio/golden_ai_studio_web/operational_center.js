(() => {
  const root = document.createElement('section');
  root.id = 'central-operacional';
  root.className = 'ops-center';
  root.innerHTML = `
    <header class="ops-title"><div><small>RADAR MACRO · FLUXO OPERACIONAL</small><h2>Central Operacional</h2></div><span id="opsUpdated">Sincronizando dados reais...</span></header>
    <section class="ops-sessions" id="opsSessions"></section>
    <div class="ops-grid">
      <article class="ops-panel ops-pipeline"><header><b>PIPELINE DE VALIDAÇÃO</b><span>estado atual</span></header><div class="pipeline" id="opsPipeline"></div></article>
      <article class="ops-panel"><header><b>RANKING DE OPORTUNIDADES</b><span>scanner MT5</span></header><div class="ranking" id="opsRanking"><div class="ops-empty">Executando scanner...</div></div></article>
      <article class="ops-panel"><header><b>AGENDA E BLOQUEIOS</b><span>próximos eventos</span></header><div class="ops-events" id="opsEvents"><div class="ops-empty">Consultando agenda...</div></div></article>
      <article class="ops-panel"><header><b>DESEMPENHO AUDITÁVEL</b><span>diário real</span></header><div class="performance" id="opsPerformance"><div class="ops-empty">Carregando histórico...</div></div></article>
    </div>`;
  document.querySelector('.terminal').after(root);
  const navButton = document.createElement('button');
  navButton.className = 'rail-btn'; navButton.dataset.scroll = 'central-operacional';
  navButton.innerHTML = '<b>◎</b>Operação';
  document.querySelector('.rail-nav').appendChild(navButton);
  const $ = id => document.getElementById(id), fmt = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 });
  const api = async (path, body = {}) => { const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); return r.json(); };
  function sessions() {
    const hour = new Date().getUTCHours() + new Date().getUTCMinutes() / 60;
    const rows = [['JP','Tóquio',0,3],['GB','Londres',7,12],['★','Sobreposição',12,15],['US','Nova York',13,17]];
    $('opsSessions').innerHTML = rows.map(([code,name,start,end]) => { const active=hour>=start&&hour<end; return `<div class="session ${active?'active':''}"><b>${code}</b><span>${name}</span><strong>${String(start).padStart(2,'0')}–${String(end).padStart(2,'0')} UTC</strong><small>${active?'ATIVA':'AGUARDA'}</small></div>`; }).join('');
  }
  function pipeline(overview, radar, risk) {
    const sources=overview?.sources||[], online=sources.filter(x=>['online','ready'].includes(x.state)).length, sourceOk=online>0;
    const events=overview?.economic_calendar||[], high=events.filter(x=>Number(x.importance)>=3).length;
    const best=radar?.radar?.[0], steps=[
      ['01','FONTES',sourceOk,`${online}/${sources.length} disponíveis`],['02','SESSÃO',true,'relógio UTC ativo'],
      ['03','MACRO',events.length?high===0:null,events.length?(high?`${high} evento(s) de alto impacto`:'sem bloqueio alto'):'agenda indisponível'],['04','SPREAD',best?best.spread<100:null,best?`${fmt.format(best.spread)} pts`:'aguardando scanner'],
      ['05','TENDÊNCIA',best?best.best_direction!=='NEUTRO':null,best?.best_direction||'sem leitura'],['06','MOMENTUM',best?best.score_total>=50:null,best?`score ${fmt.format(best.score_total)}`:'sem leitura'],
      ['07','MTF',best?[best.trend_h4,best.trend_h1,best.trend_m15].filter(Boolean).length===3:null,'H4 · H1 · M15'],['08','RISCO',risk?.ok===true,risk?.ok?'motor carregado':'indisponível'],
      ['09','VALIDAÇÃO',best?best.validation?.status!=='INCONCLUSIVO':null,best?.validation?.status||'sem amostra']];
    $('opsPipeline').innerHTML=steps.map(([n,name,ok,detail])=>`<div class="pipe-step ${ok===true?'pass':ok===false?'block':'wait'}"><small>${n}</small><b>${name}</b><span>${detail}</span></div>`).join('');
  }
  function ranking(data) {
    const rows=(data?.radar||[]).slice(0,8);
    $('opsRanking').innerHTML=rows.length?rows.map((x,i)=>{const v=x.validation||{},sample=Number(v.total_trades||0),validated=sample>=30;return `<div class="rank-row"><em>${String(i+1).padStart(2,'0')}</em><div><b>${x.symbol} <span class="${x.best_direction==='BUY'?'positive':x.best_direction==='SELL'?'negative':''}">${x.best_direction||'NEUTRO'}</span></b><small>${x.best_setup_name||x.regime||'Sem setup'} · ${x.session||'sessão n/d'}</small></div><strong>${fmt.format(x.best_readiness||x.score_total||0)}</strong><div class="rank-proof ${validated?'valid':'pending'}">${validated?`${sample} trades · EV ${fmt.format(v.expectancy_r)}R`:'histórico insuficiente'}</div></div>`}).join(''):'<div class="ops-empty">Scanner sem oportunidades disponíveis.</div>';
  }
  function events(overview) {
    const rows=(overview?.economic_calendar||[]).slice(0,6);
    $('opsEvents').innerHTML=rows.length?rows.map(e=>`<div class="event-row impact-${e.importance||1}"><time>${new Date(e.date).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}</time><div><b>${e.currency||e.country||''} · ${e.event}</b><small>Anterior ${e.previous||'–'} · Consenso ${e.forecast||'–'} · Real ${e.actual||'–'}</small></div><strong>${Number(e.importance)>=3?'ALTO':Number(e.importance)===2?'MÉDIO':'BAIXO'}</strong></div>`).join(''):`<div class="ops-empty">Agenda real indisponível. Configure o Trading Economics; nenhum evento fictício será exibido.</div>`;
  }
  function performance(data) {
    const s=data?.stats||{}, total=Number(s.total_trades||0), rr=Number(s.avg_rr||0), enough=total>=30, rrValid=Number.isFinite(rr)&&Math.abs(rr)<=20;
    const metrics=[['OPERAÇÕES',total],['WIN RATE',enough?fmt.format(s.win_rate)+'%':'sem amostra'],['RR MÉDIO',enough&&rrValid?fmt.format(rr)+'R':'inconsistente'],['PENDENTES',s.pending||0]];
    $('opsPerformance').innerHTML=`<div class="metric-grid">${metrics.map(([k,v])=>`<div><small>${k}</small><b>${v}</b></div>`).join('')}</div><div class="audit-state ${enough&&rrValid?'good':'warn'}">${!enough?`São necessárias pelo menos 30 operações resolvidas; existem ${total}. O painel não transforma score em probabilidade.`:!rrValid?'O win rate possui amostra, mas o RR médio do diário está fora de uma faixa plausível e foi bloqueado até a base ser revisada.':'Amostra mínima atingida. Métricas calculadas sobre operações resolvidas.'}</div>`;
  }
  async function load() {
    sessions();
    const [overview,radar,journal,risk]=await Promise.allSettled([api('/api/market/overview'),api('/api/scanner/radar'),api('/api/journal/stats'),api('/api/risk/status')]);
    const value=x=>x.status==='fulfilled'?x.value:{};
    pipeline(value(overview),value(radar),value(risk)); ranking(value(radar)); events(value(overview)); performance(value(journal));
    $('opsUpdated').textContent='Atualizado '+new Date().toLocaleTimeString('pt-BR')+' · dados do MT5 e fontes configuradas';
  }
  load(); setInterval(load,60000);
})();
