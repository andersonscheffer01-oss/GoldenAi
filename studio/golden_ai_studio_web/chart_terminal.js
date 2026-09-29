(() => {
  const state = { symbol: 'XAUUSD', timeframe: 'M15', indicators: new Set(['volume']), candles: [], levels: [], structureEvents: [], atr: 0, plan: null, replay: null, visible: 60, offset: 0, dragging: false, dragX: 0, dragOffset: 0, loading: false, tickLoading: false, change: 0 };
  const el = id => document.getElementById(id);
  const number = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 });
  const average = (values, period, exponential = false) => {
    const result = [], k = 2 / (period + 1); let ema = values[0];
    values.forEach((value, index) => { ema = index ? (exponential ? value * k + ema * (1 - k) : ema) : value; result.push(index < period - 1 ? null : exponential ? ema : values.slice(index - period + 1, index + 1).reduce((a, b) => a + b, 0) / period); });
    return result;
  };
  function draw() {
    const canvas = el('goldChart'), allCandles = state.candles;
    if (!canvas || !allCandles.length) return;
    const visible = Math.min(state.visible, allCandles.length), maxOffset = Math.max(0, allCandles.length - visible);
    state.offset = Math.max(0, Math.min(maxOffset, state.offset));
    const end = allCandles.length - state.offset, candles = allCandles.slice(Math.max(0, end - visible), end);
    const d = devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
    const volume = state.indicators.has('volume'), p = { l: 12, r: 64, t: 12, b: volume ? 54 : 25 };
    canvas.width = w * d; canvas.height = h * d;
    const ctx = canvas.getContext('2d'); ctx.scale(d, d);
    const low = Math.min(...candles.map(x => x.low)), high = Math.max(...candles.map(x => x.high)), span = high - low || 1;
    const pw = w - p.l - p.r, ph = h - p.t - p.b, step = pw / candles.length, body = Math.max(2, Math.min(9, step * .66));
    const y = value => p.t + (high - value) / span * ph, closes = candles.map(x => x.close);
    ctx.font = '9px Segoe UI'; ctx.fillStyle = '#839096'; ctx.strokeStyle = '#172126';
    for (let i = 0; i < 5; i++) { const yy = p.t + ph * i / 4; ctx.beginPath(); ctx.moveTo(p.l, yy); ctx.lineTo(w - p.r, yy); ctx.stroke(); ctx.fillText(number.format(high - span * i / 4), w - p.r + 7, yy + 3); }
    const plot = (values, color) => { ctx.strokeStyle = color; ctx.lineWidth = 1.3; ctx.beginPath(); let started = false; values.forEach((value, i) => { if (value == null) return; const x = p.l + (i + .5) * step; started ? ctx.lineTo(x, y(value)) : (ctx.moveTo(x, y(value)), started = true); }); ctx.stroke(); };
    if (state.indicators.has('bollinger')) { const mid = average(closes, 20), sd = closes.map((_, i) => i < 19 ? null : Math.sqrt(closes.slice(i - 19, i + 1).reduce((sum, value) => sum + (value - mid[i]) ** 2, 0) / 20)); plot(mid.map((v, i) => v == null ? null : v + 2 * sd[i]), '#6576c9'); plot(mid.map((v, i) => v == null ? null : v - 2 * sd[i]), '#6576c9'); }
    if (state.indicators.has('sma20')) plot(average(closes, 20), '#e1ad45');
    if (state.indicators.has('ema9')) plot(average(closes, 9, true), '#5aa7ff');
    const maxVolume = Math.max(...candles.map(x => x.volume || 0), 1);
    candles.forEach((candle, i) => { const x = p.l + (i + .5) * step, color = candle.close >= candle.open ? '#14b884' : '#e65761'; if (volume) { const vh = (candle.volume || 0) / maxVolume * 30; ctx.globalAlpha = .5; ctx.fillStyle = color; ctx.fillRect(x - body / 2, h - 22 - vh, body, vh); ctx.globalAlpha = 1; } ctx.strokeStyle = color; ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(x, y(candle.high)); ctx.lineTo(x, y(candle.low)); ctx.stroke(); const top = y(Math.max(candle.open, candle.close)), bottom = y(Math.min(candle.open, candle.close)); ctx.fillRect(x - body / 2, top, body, Math.max(1, bottom - top)); });
    const visibleLevels=state.levels.filter(level => level.price >= low && level.price <= high).sort((a,b)=>b.price-a.price), labelYs=[];
    visibleLevels.forEach(level => { const yy=y(level.price), support=level.kind==='support'; ctx.setLineDash(level.relevance==='alta'?[]:[5,4]); ctx.strokeStyle=support?'#19c98b':'#f25f66'; ctx.globalAlpha=level.relevance==='alta'?.9:.62; ctx.beginPath(); ctx.moveTo(p.l,yy); ctx.lineTo(w-p.r,yy); ctx.stroke(); ctx.globalAlpha=1; ctx.setLineDash([]); let labelY=yy-4; while(labelYs.some(v=>Math.abs(v-labelY)<13))labelY+=13; labelYs.push(labelY); ctx.fillStyle=support?'#19c98b':'#f25f66'; ctx.font='9px Segoe UI'; ctx.fillText(`${support?'SUPORTE':'RESISTÊNCIA'} · ${number.format(level.price)} · ${level.touches} testes`,p.l+5,labelY); });
    state.structureEvents.forEach(event=>{const index=candles.findIndex(c=>c.time===event.time);if(index<0||event.price<low||event.price>high)return;const x=p.l+(index+.5)*step,yy=y(event.price),bull=event.direction==='bullish';ctx.strokeStyle=bull?'#19c98b':'#f25f66';ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(x,yy);ctx.lineTo(x,bull?Math.max(p.t,yy-34):Math.min(p.t+ph,yy+34));ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=bull?'#19c98b':'#f25f66';ctx.font='bold 9px Segoe UI';ctx.fillText(`${event.type} ${bull?'↑':'↓'}`,Math.min(w-p.r-48,x+3),bull?Math.max(p.t+9,yy-25):Math.min(p.t+ph,yy+31));});
    if(state.plan){const planLines=[['GATILHO',state.plan.entry,'#e1ad45'],['STOP',state.plan.stop,'#f25f66'],...(state.plan.targets||[]).map((value,index)=>[`ALVO ${index+1}`,value,'#19c98b'])];planLines.forEach(([label,value,color])=>{if(!value||value<low||value>high)return;const yy=y(value);ctx.strokeStyle=color;ctx.setLineDash(label==='GATILHO'?[]:[6,4]);ctx.lineWidth=1.4;ctx.beginPath();ctx.moveTo(p.l,yy);ctx.lineTo(w-p.r,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font='bold 9px Segoe UI';ctx.fillText(`${label} · ${number.format(value)}`,Math.max(p.l,w-p.r-120),yy-4)});ctx.lineWidth=1;}
    if(state.replay&&state.replay.entry_price){const yy=y(state.replay.entry_price);if(yy>=p.t&&yy<=p.t+ph){ctx.fillStyle='rgba(225,173,69,.08)';ctx.fillRect(p.l,Math.max(p.t,yy-10),pw,20);ctx.fillStyle='#e1ad45';ctx.font='bold 9px Segoe UI';ctx.fillText(`REPLAY ${state.replay.status||''} · ${number.format(state.replay.entry_price)}`,p.l+6,yy+3)}}
    const last = candles.at(-1); ctx.setLineDash([3, 3]); ctx.strokeStyle = '#19c98b'; ctx.beginPath(); ctx.moveTo(p.l, y(last.close)); ctx.lineTo(w - p.r, y(last.close)); ctx.stroke(); ctx.setLineDash([]); ctx.fillStyle = '#138968'; ctx.fillRect(w - p.r + 3, y(last.close) - 9, 58, 18); ctx.fillStyle = '#fff'; ctx.fillText(number.format(last.close), w - p.r + 7, y(last.close) + 3);
    canvas.onmousemove = event => { if (state.dragging) { const delta = Math.round((event.clientX - state.dragX) / Math.max(3, step)); state.offset = state.dragOffset + delta; draw(); return; } const box = canvas.getBoundingClientRect(), i = Math.max(0, Math.min(candles.length - 1, Math.floor((event.clientX - box.left - 12) / Math.max(1, (box.width - 76) / candles.length)))), c = candles[i]; el('chartStatus').textContent = `${state.timeframe} · ${new Date(c.time * 1000).toLocaleString('pt-BR')} · A ${number.format(c.open)}  M ${number.format(c.high)}  m ${number.format(c.low)}  F ${number.format(c.close)}  Vol ${number.format(c.volume)}`; };
    canvas.onmouseleave = () => el('chartStatus').textContent = state.timeframe + ' · MetaTrader 5';
  }
  let loadSequence=0;
  async function load(timeframe = state.timeframe, live = false) {
    state.loading=true; const requestSequence=++loadSequence; const requestSymbol=state.symbol; state.timeframe = timeframe; if(!live)el('chartStatus').textContent = timeframe + ' · carregando MT5';
    try { const response = await fetch('/api/market/chart', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbol: requestSymbol, timeframe }) }); const data = await response.json(); if (!data.ok) throw new Error(data.error); if(requestSequence!==loadSequence||requestSymbol!==state.symbol)return; const wasAtLiveEdge=state.offset===0; state.candles = data.candles; state.levels=data.levels||[]; state.structureEvents=data.structure_events||[];state.atr=data.atr||0; state.change=data.change; if(!live||wasAtLiveEdge)state.offset = 0; el('chartQuote').innerHTML = `<strong>${number.format(data.price)}</strong><span class="${data.change >= 0 ? 'up-text' : 'down-text'}">${data.change >= 0 ? '+' : ''}${number.format(data.change)}%</span><small style="margin-left:10px;color:#81949c">RSI ${number.format(data.rsi)} · ${state.levels.length} níveis · ${state.structureEvents.length} estruturas · AO VIVO</small>`; el('chartStatus').textContent = timeframe + ' · ' + data.source + ' · atualizado ' + new Date().toLocaleTimeString('pt-BR'); const clean=state.symbol.replace(/[^A-Z]/g,''); document.querySelector('.chart-symbol b').textContent=clean.length===6?clean.slice(0,3)+'/'+clean.slice(3):state.symbol; document.querySelector('.chart-symbol small').textContent='Análise técnica · '+data.source; draw(); window.dispatchEvent(new CustomEvent('golden-chart-loaded',{detail:data})); } catch (error) { if(requestSequence===loadSequence)el('chartStatus').textContent = 'Falha: ' + error.message; } finally {state.loading=false;}
  }
  async function loadTick(){
    if(state.tickLoading||!state.candles.length)return; state.tickLoading=true;
    try{const response=await fetch('/api/market/tick',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:state.symbol})}),tick=await response.json();if(!tick.ok)throw new Error(tick.error);const candle=state.candles.at(-1);candle.close=tick.price;candle.high=Math.max(candle.high,tick.price);candle.low=Math.min(candle.low,tick.price);const strong=el('chartQuote').querySelector('strong');if(strong)strong.textContent=number.format(tick.price);el('chartStatus').textContent=`${state.timeframe} · TICK AO VIVO · Bid ${number.format(tick.bid)} · Ask ${number.format(tick.ask)} · Spread ${number.format(tick.spread)} pts · ${new Date(tick.time_msc).toLocaleTimeString('pt-BR')}`;draw();}catch(error){el('chartStatus').textContent='Tick: '+error.message}finally{state.tickLoading=false;}
  }
  el('chartTimeframes').addEventListener('click', event => { const button = event.target.closest('[data-tf]'); if (!button) return; document.querySelectorAll('.tf-button').forEach(x => x.classList.toggle('active', x === button)); load(button.dataset.tf); });
  el('indicatorToggle').onclick = event => { event.stopPropagation(); el('indicatorPopover').hidden = !el('indicatorPopover').hidden; };
  el('indicatorPopover').onchange = event => { event.target.checked ? state.indicators.add(event.target.value) : state.indicators.delete(event.target.value); draw(); };
  document.addEventListener('click', event => { if (!event.target.closest('.indicator-menu')) el('indicatorPopover').hidden = true; });
  const tools = el('chartTimeframes'), indicatorMenu = tools.querySelector('.indicator-menu');
  const makeButton = (id, text, title) => { const button = document.createElement('button'); button.className = 'indicator-button'; button.id = id; button.textContent = text; button.title = title; tools.insertBefore(button, indicatorMenu); return button; };
  const zoom = amount => { state.visible = Math.max(18, Math.min(100, state.visible + amount)); draw(); };
  makeButton('chartZoomIn', '+', 'Ampliar gráfico').onclick = () => zoom(-10);
  makeButton('chartZoomOut', '−', 'Reduzir gráfico').onclick = () => zoom(10);
  makeButton('chartReset', '↺', 'Voltar ao candle atual').onclick = () => { state.visible = 60; state.offset = 0; draw(); };
  const canvas = el('goldChart');
  canvas.addEventListener('wheel', event => { event.preventDefault(); zoom(event.deltaY > 0 ? 8 : -8); }, { passive: false });
  canvas.addEventListener('mousedown', event => { state.dragging = true; state.dragX = event.clientX; state.dragOffset = state.offset; canvas.style.cursor = 'grabbing'; });
  addEventListener('mouseup', () => { state.dragging = false; canvas.style.cursor = 'crosshair'; });
  canvas.addEventListener('dblclick', () => { state.visible = 60; state.offset = 0; draw(); });
  window.GoldenChart={select(symbol){state.symbol=symbol;state.plan=null;state.replay=null;load(state.timeframe)},reload(){load(state.timeframe)},setPlan(plan){state.plan=plan;state.replay=null;draw()},setReplay(record){state.replay=record;state.plan=null;draw()},clearOverlays(){state.plan=null;state.replay=null;draw()},getState(){return {symbol:state.symbol,timeframe:state.timeframe,levels:state.levels,candles:state.candles,structureEvents:state.structureEvents,atr:state.atr,plan:state.plan}}};
  addEventListener('resize', draw); setTimeout(() => load(), 1200); setInterval(()=>{if(!document.hidden)loadTick()},500); setInterval(()=>{if(!document.hidden)load(state.timeframe,true)},15000);
})();
