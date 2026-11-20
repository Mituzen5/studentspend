'use strict';
const $ = id => document.getElementById(id);
const CATS = [['Food','🍔'],['Movies & fun','🎬'],['Groceries','🛒'],['Travel','🚌'],['Shopping','🛍️'],['Education','📚'],['Bills & mobile','📱'],['Health','🩺'],['Other','📦']];
const CAT_ICON = Object.fromEntries([...CATS, ['Savings','🌱']]);
const PALETTE = ['#16a36a','#4f7cff','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#ec4899','#84cc16','#94a3b8'];
const GOAL_EMOJIS = ['🎯','💻','📱','🎧','✈️','🚲','🎓','🎮','📚','🎁','🏍️','👟'];
let showAllTx = false;
let csrf = '', state = null, selectedMonth = '', registerMode = false, tab = 'dashboard';
const charts = {};

const money = n => (n < 0 ? '-₹' : '₹') + Math.abs(Math.round(Number(n) || 0)).toLocaleString('en-IN');
const pad = n => String(n).padStart(2, '0');
const localDate = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const today = () => localDate();
const monthOf = d => d.slice(0, 7);
const monthName = m => new Date(m + '-01T12:00:00').toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
const shortMonth = m => new Date(m + '-01T12:00:00').toLocaleDateString('en-IN', { month: 'short', year: '2-digit' });
const niceDate = d => new Date(d + 'T12:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
let toastTimer;
function toast(s) { const t = $('toast'); t.textContent = s; t.classList.remove('hidden'); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.add('hidden'), 2800); }

// ------------------------------------------------------------------ API
async function api(path, { method = 'GET', body, retry = true } = {}) {
  const res = await fetch(path, {
    method, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, 'X-Client-Date': today() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  if (res.status === 403 && retry && /session expired/i.test(data.error || '')) {
    await loadSession(); return api(path, { method, body, retry: false });
  }
  if (res.status === 401 && path !== '/api/login') { showAuth(); throw new Error(data.error || 'Please log in.'); }
  if (!res.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  if (data.csrf) csrf = data.csrf;
  return data;
}
async function loadSession() { const s = await (await fetch('/api/session', { credentials: 'same-origin' })).json(); csrf = s.csrf; return s; }
async function refresh(month) {
  const d = await api('/api/dashboard' + (month ? '?month=' + encodeURIComponent(month) : ''));
  apply(d);
}
function apply(d) { state = d; selectedMonth = d.month; render(); }
async function busy(btn, fn) {
  if (btn) btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message); } finally { if (btn) btn.disabled = false; }
}

// ------------------------------------------------------------------ AUTH
function auth(showRegister) {
  registerMode = showRegister;
  $('authTitle').textContent = showRegister ? 'Start your money-smart journey' : 'Your money. Your goals.';
  $('authSub').textContent = showRegister ? 'Create your personal student budget space.' : 'Sign in to make your student budget work smarter.';
  ['nameField', 'allowanceField', 'strengthWrap'].forEach(id => $(id).classList.toggle('hidden', !showRegister));
  $('authSubmit').textContent = showRegister ? 'Create account' : 'Login to dashboard';
  $('authSwitchText').textContent = showRegister ? 'Already have an account?' : 'New here?';
  $('authSwitch').textContent = showRegister ? 'Login' : 'Create student account';
  $('password').autocomplete = showRegister ? 'new-password' : 'current-password';
  $('authError').textContent = '';
}
function showAuth() {
  state = null; $('loading').classList.add('hidden');
  $('appView').classList.add('hidden'); $('bottomNav').classList.add('hidden'); $('fab').classList.add('hidden');
  $('authView').classList.remove('hidden'); closeModal();
}
$('authSwitch').onclick = () => auth(!registerMode);
$('authSwitch').onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); auth(!registerMode); } };
$('pwToggle').onclick = () => { const p = $('password'), show = p.type === 'password'; p.type = show ? 'text' : 'password'; $('pwToggle').textContent = show ? 'Hide' : 'Show'; };
$('password').oninput = () => {
  if (!registerMode) return;
  const v = $('password').value; let s = 0;
  if (v.length >= 8) s++; if (/[A-Za-z]/.test(v) && /\d/.test(v)) s++; if (v.length >= 12) s++; if (/[^A-Za-z0-9]/.test(v)) s++;
  const lv = [['0%', '#e05252', 'Use 8+ characters with letters and numbers.'], ['30%', '#e05252', 'Weak — add more characters.'], ['60%', '#e6a23c', 'Okay — add symbols or length.'], ['80%', '#16a36a', 'Strong password.'], ['100%', '#16a36a', 'Very strong password!']][s];
  $('strengthBar').style.width = lv[0]; $('strengthBar').style.background = lv[1]; $('strengthText').textContent = lv[2];
};
$('authForm').onsubmit = e => {
  e.preventDefault();
  const username = $('username').value.trim().toLowerCase(), password = $('password').value;
  $('authError').textContent = '';
  if (!username || !password) { $('authError').textContent = 'Enter your student ID and password.'; return; }
  busy($('authSubmit'), async () => {
    try {
      if (registerMode) await api('/api/register', { method: 'POST', body: { username, password, name: $('displayName').value.trim(), allowance: Number($('regAllowance').value) || 0 } });
      else await api('/api/login', { method: 'POST', body: { username, password } });
      await openApp(); $('authForm').reset(); toast(registerMode ? 'Welcome to StudentSpend! 🎉' : 'Welcome back!');
    } catch (err) { $('authError').textContent = err.message; }
  });
};
async function openApp() {
  await refresh();
  $('authView').classList.add('hidden'); $('loading').classList.add('hidden');
  $('appView').classList.remove('hidden'); $('bottomNav').classList.remove('hidden'); $('fab').classList.remove('hidden');
  route();
}
$('logoutBtn').onclick = () => busy($('logoutBtn'), async () => { await api('/api/logout', { method: 'POST' }); showAuth(); auth(false); location.hash = ''; });

// ------------------------------------------------------------------ ROUTING
function route() {
  const t = (location.hash || '#dashboard').slice(1);
  tab = ['dashboard', 'reports', 'goals', 'settings'].includes(t) ? t : 'dashboard';
  ['dashboard', 'reports', 'goals', 'settings'].forEach(x => $('view-' + x).classList.toggle('hidden', x !== tab));
  document.querySelectorAll('[data-tab]').forEach(a => { a.classList.toggle('active', a.dataset.tab === tab); a.setAttribute('aria-current', a.dataset.tab === tab ? 'page' : 'false'); });
  $('monthHeader').classList.toggle('hidden', !['dashboard', 'reports'].includes(tab));
  $('fab').classList.toggle('hidden', !state || tab === 'settings');
  if (state) render();
  window.scrollTo({ top: 0 });
}
window.addEventListener('hashchange', route);
$('monthSelect').onchange = e => busy(null, () => refresh(e.target.value));

// ------------------------------------------------------------------ RENDER
function render() {
  if (!state) return;
  const d = state, s = d.summary, u = d.user;
  $('studentName').textContent = u.name; $('avatar').textContent = (u.name[0] || 'S').toUpperCase();
  $('userGreeting').textContent = '@' + u.username;
  $('monthTitle').textContent = monthName(d.month) + ' overview';
  $('cycleText').textContent = `Cycle: ${d.month} · ${s.expenseCount} expense entries` + (d.month === d.currentMonth ? ' · current month' : ' · closed');
  $('monthSelect').innerHTML = d.months.map(m => `<option value="${m}" ${m === d.month ? 'selected' : ''}>${monthName(m)}${m === d.currentMonth ? ' (current)' : ''}</option>`).join('');
  const sc = d.report.score, ring = $('scoreRing');
  ring.style.setProperty('--p', sc); ring.style.setProperty('--c', sc >= 70 ? '#16a36a' : sc >= 45 ? '#e6a23c' : '#e05252');
  $('scoreValue').textContent = sc;
  $('scoreText').textContent = s.total <= 0 ? 'Add your allowance to start' : sc >= 80 ? 'Excellent money habits!' : sc >= 60 ? 'Good — room to improve' : sc >= 40 ? 'Needs attention' : 'Time to slow down';
  if (tab === 'dashboard') renderDashboard();
  if (tab === 'reports') renderReports();
  if (tab === 'goals') renderGoals();
  if (tab === 'settings') renderSettings();
}

function renderDashboard() {
  const d = state, s = d.summary, r = d.recommendation;
  $('totalMoney').textContent = money(s.total); $('totalSpent').textContent = money(s.spent); $('totalSaved').textContent = money(s.saved);
  $('balance').textContent = money(s.balance); $('balance').classList.toggle('neg', s.balance < 0);
  $('moneyNote').textContent = `${money(s.allowance)} allowance + ${money(s.carry)} carried`;
  $('spentNote').textContent = s.expenseCount + ' recorded purchases';
  $('balanceNote').textContent = r.isCurrent ? 'Ready for the rest of the month' : (s.balance > 0 ? 'Carried into next month' : 'Nothing left to carry');
  const pct = Math.min(100, s.usedPct);
  $('usedPercent').textContent = Math.round(s.usedPct) + '%'; $('budgetBar').style.width = pct + '%';
  $('budgetProgress').className = 'progress' + (pct >= 90 ? ' danger' : pct >= 75 ? ' warning' : '');
  $('healthTag').textContent = s.usedPct >= 100 ? 'Over budget' : s.usedPct >= 80 ? 'Be careful' : 'On track';
  const lvl = { red: 'red', amber: '', green: 'green', info: 'info' };
  $('warningArea').innerHTML = d.warnings.map(w => `<div class="alert ${lvl[w.level]}"><span>${w.icon}</span><div><b>${esc(w.title)}</b>${esc(w.text)}</div></div>`).join('');

  if (r.isCurrent) {
    $('dailyTitle').textContent = "Today's safe-to-spend budget";
    $('dailyBudget').textContent = money(r.dailyLimit);
    $('dailyHint').textContent = s.balance < 0 ? 'You are over budget. Avoid extra spending if possible.' : `You have ${r.remainingDays} day(s) in this cycle. Try to stay within this daily limit.`;
    $('dailyGrid').innerHTML = mini('Spent today', r.spentToday) + mini('Left today', r.leftToday, r.leftToday < 0) +
      (r.goalReserve > 0 && r.goalAwareDaily > 0 ? mini('Goal-friendly / day', r.goalAwareDaily) : mini('This week', r.weeklyLimit));
  } else {
    $('dailyTitle').textContent = 'Cycle closed';
    $('dailyBudget').textContent = money(Math.max(0, s.balance));
    $('dailyHint').textContent = s.balance > 0 ? 'This unused balance was carried forward to the next month.' : 'No balance was left to carry forward.';
    $('dailyGrid').innerHTML = mini('Avg / day', r.avgDaily) + mini('Spent', s.spent) + mini('Saved', s.saved);
  }

  const cats = d.categories.filter(c => c.spent > 0 || c.limit).sort((a, b) => b.spent - a.spent);
  $('categoryList').innerHTML = cats.length ? cats.map(c => {
    const w = c.limit ? Math.min(100, c.limitPct) : c.share, cls = c.limit ? (c.limitPct >= 100 ? 'over' : c.limitPct >= 80 ? 'near' : '') : '';
    return `<div class="cat-row"><div class="cat-icon">${c.icon}</div><div><div class="cat-name">${esc(c.name)} ${c.limit ? `<span class="cat-limit">· limit ${money(c.limit)}</span>` : `<span class="cat-limit">· ${c.share}%</span>`}</div><div class="cat-track"><span class="${cls}" style="width:${w}%"></span></div></div><div class="cat-amount">${money(c.spent)}</div></div>`;
  }).join('') : '<div class="empty">No expenses yet. Add your first expense to see the breakdown.</div>';

  $('carryInfo').textContent = s.carry ? `${money(s.carry)} carried forward from your previous month. This amount is already included in your monthly money.` : 'No previous balance was carried into this cycle yet.';
  const hist = d.history.slice(-3);
  $('cycleList').innerHTML = hist.map(h => `<div class="cycle-row"><span>${shortMonth(h.month)} · ${money(h.allowance)} + ${money(h.carry)}</span><span>${h.month === d.currentMonth ? 'balance' : 'carried'} <b>${money(Math.max(0, h.balance))}</b></span></div>`).join('');

  const ch = d.challenge;
  $('challengeBtn').textContent = ch.doneToday ? '✅ Challenge completed today' : "🎯 Start today's challenge";
  $('challengeBtn').disabled = ch.doneToday;
  $('streakBadge').textContent = '🔥 ' + ch.streak + ' day' + (ch.streak === 1 ? '' : 's');
  $('streakBar').innerHTML = Array.from({ length: 7 }, (_, i) => `<i class="${i < Math.min(7, ch.streak) ? 'on' : ''}"></i>`).join('');
  $('challengeStatus').textContent = ch.doneToday ? `✅ Challenge completed today. Nice work! ${ch.thisMonth} no-spend day(s) this month.` : (ch.streak ? `Keep your ${ch.streak}-day streak alive!` : 'Your challenge is ready when you are.');

  $('goalsList').innerHTML = d.goals.length ? d.goals.slice(0, 4).map(g => `<div class="goal"><div class="goal-top"><span>${esc(g.emoji)} ${esc(g.name)}</span><span>${money(g.saved)} / ${money(g.target)}</span></div><div class="progress" style="margin:9px 0 5px"><span style="width:${g.pct}%"></span></div><div class="goal-top"><small>${Math.round(g.pct)}% of your goal${g.perDay ? ` · save ${money(g.perDay)}/day` : ''}</small>${g.completed ? '<span class="status completed">Done 🎉</span>' : `<button class="secondary small goal-quick" data-action="contribute" data-id="${g.id}">+ Add</button>`}</div></div>`).join('') + (d.goals.length > 4 ? `<a class="link" href="#goals" style="display:block;margin-top:10px;font-size:13px">View all ${d.goals.length} goals →</a>` : '')
    : '<div class="empty">No savings goal yet. Create one for something you really want!</div>';

  const rep = d.report;
  $('insights').innerHTML = `<p>🧾 You spent <b>${money(rep.needs)}</b> on other categories and <b>${money(rep.wants)}</b> on movies and shopping this month.</p><p>🌱 Your savings rate is <b>${Math.round(rep.savingsRate)}%</b> of your available monthly money.</p><p>💚 ${s.saved > 0 ? 'Great job putting money aside!' : 'Try saving a small amount as soon as your allowance arrives.'}</p>` +
    (rep.spendChangePct !== null ? `<p>${rep.spendChangePct <= 0 ? '📉' : '📈'} Spending is <b>${Math.abs(Math.round(rep.spendChangePct))}% ${rep.spendChangePct <= 0 ? 'lower' : 'higher'}</b> than last month.</p>` : '') +
    (rep.topCategory ? `<p>${rep.topCategory.icon} Top category: <b>${esc(rep.topCategory.name)}</b> (${money(rep.topCategory.spent)}).</p>` : '');
  $('tipText').textContent = tipFor(d);
  renderTransactions();
  drawTrend();
}
const mini = (label, val, neg) => `<div class="mini"><small>${label}</small><b class="${neg ? 'neg' : ''}">${money(val)}</b></div>`;
function tipFor(d) {
  const r = d.report, s = d.summary;
  if (s.total <= 0) return 'Set your monthly allowance first so we can plan your daily budget.';
  if (r.wantsPct > 40) return 'Try a 24-hour rule: wait a day before any "want" purchase over ₹300.';
  if (s.saved === 0) return 'Save a little first, then plan your spending with what remains.';
  if (d.recommendation.isCurrent && d.recommendation.leftToday > 0) return `You still have ${money(d.recommendation.leftToday)} safe to spend today — or save it for a goal!`;
  return 'Cook or carry lunch twice a week — it adds up to big monthly savings.';
}

function filteredTx() {
  const q = $('txSearch').value.trim().toLowerCase(), f = $('txFilter').value;
  return state.transactions.filter(t => (!f || t.type === f) && (!q || (t.note + ' ' + t.category).toLowerCase().includes(q)));
}
function renderTransactions() {
  const all = filteredTx(), rows = showAllTx ? all : all.slice(0, 10), goals = Object.fromEntries(state.goals.map(g => [g.id, g]));
  const detail = t => esc(t.note || t.category) + (t.goalId && goals[t.goalId] ? ` <span class="tag">${esc(goals[t.goalId].emoji)} ${esc(goals[t.goalId].name)}</span>` : '');
  const amt = t => `<span class="${t.type === 'expense' ? 'amount-out' : 'amount-save'}">${t.type === 'expense' ? '-' : '+'}${money(t.amount)}</span>`;
  const acts = t => `<div class="row-actions"><button class="secondary" data-action="edit-tx" data-id="${t.id}" aria-label="Edit">✎ Edit</button><button class="danger" data-action="delete-tx" data-id="${t.id}" aria-label="Delete">× Delete</button></div>`;
  const none = state.transactions.length ? 'No matching activity.' : 'No activity yet — add an expense or savings entry.';
  $('transactionsBody').innerHTML = rows.length ? rows.map(t => `<tr><td>${t.date}</td><td>${detail(t)}</td><td><span class="tag">${esc(t.category)}</span></td><td>${t.type === 'expense' ? 'Expense' : 'Saving'}</td><td>${amt(t)}</td><td>${acts(t)}</td></tr>`).join('') : `<tr><td colspan="6" class="empty">${none}</td></tr>`;
  $('txMore').classList.toggle('hidden', all.length <= 10);
  $('txMore').textContent = showAllTx ? 'Show less' : `Show all ${all.length} entries`;
  $('txCards').innerHTML = rows.length ? rows.map(t => `<div class="tx-card"><div class="cat-icon">${CAT_ICON[t.category] || '📦'}</div><div><div class="cat-name">${detail(t)}</div><small class="muted">${niceDate(t.date)} · ${esc(t.category)}</small></div><div>${amt(t)}</div>${acts(t)}</div>`).join('') : `<div class="empty">${none}</div>`;
}
$('txMore').onclick = () => { showAllTx = !showAllTx; renderTransactions(); };
$('txSearch').oninput = renderTransactions; $('txFilter').onchange = renderTransactions;

// ------------------------------------------------------------------ CHARTS
function themeColors() {
  const cs = getComputedStyle(document.documentElement);
  return { ink: cs.getPropertyValue('--muted').trim() || '#718096', grid: cs.getPropertyValue('--line').trim() || '#e8edf4' };
}
function makeChart(id, config) {
  if (typeof Chart === 'undefined') return;
  const { ink, grid } = themeColors();
  Chart.defaults.color = ink; Chart.defaults.font.family = 'Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif';
  if (config.options?.scales) Object.values(config.options.scales).forEach(sc => { sc.grid = { color: grid, ...(sc.grid || {}) }; sc.border = { display: false }; });
  if (charts[id]) { charts[id].destroy(); }
  charts[id] = new Chart($(id), config);
}
const moneyTick = { callback: v => '₹' + Number(v).toLocaleString('en-IN') };
const tooltipMoney = { callbacks: { label: c => ` ${c.dataset.label ? c.dataset.label + ': ' : ''}${money(c.parsed.y ?? c.parsed)}` } };
function drawTrend() {
  const s = state.series;
  makeChart('trendChart', {
    type: 'line',
    data: { labels: s.labels, datasets: [
      { label: 'You', data: s.cumulative, borderColor: '#16a36a', backgroundColor: '#16a36a22', fill: true, tension: .3, pointRadius: 0, pointHoverRadius: 5, borderWidth: 2.5 },
      { label: 'Ideal pace', data: s.ideal, borderColor: '#94a3b8', borderDash: [6, 5], pointRadius: 0, borderWidth: 1.5, fill: false },
    ] },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: false }, tooltip: { ...tooltipMoney, callbacks: { ...tooltipMoney.callbacks, title: i => 'Day ' + i[0].label } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, ticks: { ...moneyTick, maxTicksLimit: 5 } } } },
  });
}
function renderReports() {
  const d = state, s = d.summary, r = d.report;
  const kpi = (label, icon, val, note, neg) => `<div class="card kpi"><div class="stat-top">${label} <span class="stat-icon">${icon}</span></div><div class="stat-value ${neg ? 'neg' : ''}">${val}</div><div class="stat-note">${note}</div></div>`;
  $('kpis').innerHTML =
    kpi('Average per day', '📆', money(r.avgDaily), `over ${r.daysTracked} day(s)`) +
    kpi('Savings rate', '🌱', Math.round(r.savingsRate) + '%', `${money(s.saved)} saved`) +
    kpi('vs last month', r.spendChangePct > 0 ? '📈' : '📉', r.spendChangePct === null ? '—' : (r.spendChangePct > 0 ? '+' : '') + Math.round(r.spendChangePct) + '%', r.prevSpent === null ? 'No previous month' : `${money(r.prevSpent)} last month`, r.spendChangePct > 0) +
    kpi('No-spend days', '🧘', r.noSpendDays, `out of ${r.daysTracked} day(s)`);
  const cats = d.categories.filter(c => c.spent > 0);
  makeChart('catChart', {
    type: 'doughnut',
    data: { labels: cats.length ? cats.map(c => c.icon + ' ' + c.name) : ['No spending yet'], datasets: [{ data: cats.length ? cats.map(c => c.spent) : [1], backgroundColor: cats.length ? cats.map(c => PALETTE[CATS.findIndex(x => x[0] === c.name)]) : ['#e8edf4'], borderWidth: 0, hoverOffset: 10 }] },
    options: { maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, usePointStyle: true } }, tooltip: cats.length ? { callbacks: { label: c => ` ${money(c.parsed)} (${Math.round(c.parsed / s.spent * 100)}%)` } } : { enabled: false } } },
  });
  const paceLimit = Math.max(0, s.total - s.saved) / d.series.labels.length || Infinity;
  makeChart('dailyChart', {
    type: 'bar',
    data: { labels: d.series.labels, datasets: [{ label: 'Spent', data: d.series.daily, backgroundColor: d.series.daily.map(v => v > paceLimit ? '#e05252' : '#16a36a'), borderRadius: 5, maxBarThickness: 18 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { ...tooltipMoney, callbacks: { ...tooltipMoney.callbacks, title: i => niceDate(d.month + '-' + pad(i[0].label)) } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } }, y: { beginAtZero: true, ticks: { ...moneyTick, maxTicksLimit: 5 } } } },
  });
  makeChart('historyChart', {
    type: 'bar',
    data: { labels: d.history.map(h => shortMonth(h.month)), datasets: [
      { label: 'Spent', data: d.history.map(h => h.spent), backgroundColor: '#e05252', borderRadius: 6, maxBarThickness: 26 },
      { label: 'Saved', data: d.history.map(h => h.saved), backgroundColor: '#16a36a', borderRadius: 6, maxBarThickness: 26 },
      { label: 'Left / carried', data: d.history.map(h => Math.max(0, h.balance)), backgroundColor: '#4f7cff', borderRadius: 6, maxBarThickness: 26 },
    ] },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, usePointStyle: true } }, tooltip: tooltipMoney },
      scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { ...moneyTick, maxTicksLimit: 5 } } } },
  });
  const nw = r.needs + r.wants > 0;
  makeChart('needsChart', {
    type: 'doughnut',
    data: { labels: nw ? ['Needs', 'Wants'] : ['No spending yet'], datasets: [{ data: nw ? [r.needs, r.wants] : [1], backgroundColor: nw ? ['#4f7cff', '#f59e0b'] : ['#e8edf4'], borderWidth: 0, hoverOffset: 10 }] },
    options: { maintainAspectRatio: false, cutout: '62%', plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, usePointStyle: true } }, tooltip: nw ? { callbacks: { label: c => ` ${money(c.parsed)} (${Math.round(c.parsed / (r.needs + r.wants) * 100)}%)` } } : { enabled: false } } },
  });
  $('reportSub').textContent = `Highlights for ${monthName(d.month)}`;
  const lines = [];
  lines.push(`💳 You had <b>${money(s.total)}</b> to manage (${money(s.allowance)} allowance + ${money(s.carry)} carried forward).`);
  lines.push(`🛍️ You spent <b>${money(s.spent)}</b> across ${s.expenseCount} purchase(s) and saved <b>${money(s.saved)}</b>.`);
  if (r.topCategory) lines.push(`${r.topCategory.icon} Your biggest category was <b>${esc(r.topCategory.name)}</b> at ${money(r.topCategory.spent)}.`);
  if (r.biggest) lines.push(`💸 Largest single expense: <b>${money(r.biggest.amount)}</b> — ${esc(r.biggest.note || r.biggest.category)} on ${niceDate(r.biggest.date)}.`);
  lines.push(`⚖️ Needs vs wants: <b>${100 - Math.round(r.wantsPct)}% / ${Math.round(r.wantsPct)}%</b>${r.wantsPct > 30 ? ' — try trimming wants a little.' : ' — nicely balanced!'}`);
  lines.push(d.recommendation.isCurrent ? `📅 Projected month-end spending: <b>${money(d.recommendation.projectedSpend)}</b>.` : `🔁 <b>${money(r.carriedOut)}</b> rolled over into the next month.`);
  lines.push(`🏅 Money health score: <b>${r.score}/100</b>.`);
  $('reportSummary').innerHTML = lines.map(l => `<p style="margin:6px 0">${l}</p>`).join('');
  $('historyBody').innerHTML = d.history.slice().reverse().map(h => `<tr><td>${monthName(h.month)}</td><td>${money(h.allowance)}</td><td>${money(h.carry)}</td><td class="amount-out">${money(h.spent)}</td><td class="amount-save">${money(h.saved)}</td><td>${money(h.balance)}</td></tr>`).join('');
}

function renderGoals() {
  const gs = state.goals, total = gs.reduce((a, g) => a + g.saved, 0), target = gs.reduce((a, g) => a + g.target, 0);
  const card = (label, icon, val, note) => `<div class="card"><div class="stat-top">${label} <span class="stat-icon">${icon}</span></div><div class="stat-value">${val}</div><div class="stat-note">${note}</div></div>`;
  $('goalStats').innerHTML = card('Active goals', '🎯', gs.filter(g => !g.completed).length, `${gs.filter(g => g.completed).length} completed`) + card('Saved for goals', '💰', money(total), `of ${money(target)} total`) +
    card('Overall progress', '📈', (target ? Math.round(total / target * 100) : 0) + '%', 'across all goals') + card('Saved this month', '🌱', money(state.summary.saved), 'including general savings');
  const label = { completed: 'Completed 🎉', 'on-track': 'On track', behind: 'Behind schedule', overdue: 'Deadline passed', active: 'In progress' };
  $('goalCards').innerHTML = gs.length ? gs.map(g => `<div class="card goal-card"><div class="goal-head"><div class="goal-emoji">${esc(g.emoji)}</div><div style="flex:1;min-width:0"><b>${esc(g.name)}</b><div class="muted" style="font-size:12px">${g.deadline ? 'by ' + new Date(g.deadline + 'T12:00:00').toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : 'No deadline'}</div></div><span class="status ${g.status}">${label[g.status]}</span></div>
    <div class="budget-line"><span>${money(g.saved)} of ${money(g.target)}</span><b>${Math.round(g.pct)}%</b></div><div class="progress"><span style="width:${g.pct}%"></span></div>
    <div class="goal-meta">${mini('Still needed', g.remaining)}${g.perMonth ? mini('Save / month', g.perMonth) : g.perDay ? mini('Save / day', g.perDay) : `<div class="mini"><small>Est. completion</small><b>${g.completed ? 'Done' : g.eta ? shortMonth(g.eta) : '—'}</b></div>`}</div>
    ${g.perDay ? `<p class="hint" style="margin:-4px 0 12px">💡 That's about ${money(g.perDay)} a day for ${g.daysLeft} day(s).</p>` : ''}
    <div class="goal-actions">${g.completed ? '' : `<button class="small" data-action="contribute" data-id="${g.id}">+ Add money</button>`}<button class="secondary small" data-action="edit-goal" data-id="${g.id}">✎ Edit</button><button class="danger small" data-action="delete-goal" data-id="${g.id}">Delete</button></div></div>`).join('')
    : '<div class="card empty" style="grid-column:1/-1">No savings goals yet. Tap “New goal” to create your first one — a laptop, a trip, or an emergency fund!</div>';
}

function renderSettings() {
  const u = state.user;
  $('profileId').textContent = 'Student ID: @' + u.username;
  if (document.activeElement !== $('profileName')) $('profileName').value = u.name;
  $('defaultAllowance').textContent = money(u.defaultAllowance);
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  $('darkToggle').classList.toggle('on', dark); $('darkToggle').setAttribute('aria-pressed', dark);
  $('limitFields').innerHTML = CATS.map(([n, i]) => `<div class="field"><label>${i} ${n}</label><input type="number" min="0" step="1" inputmode="numeric" data-cat="${esc(n)}" value="${u.limits[n] ?? ''}" placeholder="No limit"></div>`).join('');
}

// ------------------------------------------------------------------ MODALS
function modal(title, body, onSave, { saveText = 'Save', sub = 'Add the details below.', danger = false } = {}) {
  $('modalHost').innerHTML = `<div class="modal-back" id="backdrop"><form class="modal" id="modalForm" role="dialog" aria-modal="true" aria-labelledby="modalTitle" novalidate><h2 id="modalTitle">${title}</h2><div class="muted" style="font-size:13px">${sub}</div>${body}<div class="form-error" id="modalError" role="alert"></div><div class="modal-actions"><button type="button" class="secondary" id="cancelModal">Cancel</button><button id="saveModal" class="${danger ? 'danger' : ''}">${saveText}</button></div></form></div>`;
  $('cancelModal').onclick = closeModal;
  $('backdrop').onclick = e => { if (e.target.id === 'backdrop') closeModal(); };
  $('modalForm').onsubmit = e => {
    e.preventDefault(); $('modalError').textContent = '';
    const btn = $('saveModal'); btn.disabled = true;
    Promise.resolve().then(onSave).catch(err => { if ($('modalError')) $('modalError').textContent = err.message; }).finally(() => { if ($('saveModal')) btn.disabled = false; });
  };
  const first = $('modalHost').querySelector('input,select'); if (first) setTimeout(() => first.focus(), 30);
}
function closeModal() { $('modalHost').innerHTML = ''; }
document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('modalHost').innerHTML) closeModal(); });
function confirmBox(title, text, saveText = 'Delete') { return new Promise(res => { modal(title, '', () => { closeModal(); res(true); }, { saveText, sub: text, danger: true }); $('cancelModal').onclick = () => { closeModal(); res(false); }; }); }
const fail = msg => { throw new Error(msg); };

function entryModal(type, tx, presetGoal) {
  const isExp = type === 'expense', t = tx || {};
  const defDate = t.date || (selectedMonth === state.currentMonth ? today() : selectedMonth + '-' + pad(new Date(selectedMonth.slice(0, 4), selectedMonth.slice(5), 0).getDate()));
  const goalSel = state.goals.filter(g => !g.completed || g.id === t.goalId || g.id === presetGoal);
  const body = `<div class="field"><label for="entryAmount">Amount (₹)</label><input id="entryAmount" type="number" min="1" step="0.01" inputmode="decimal" placeholder="e.g. 120" value="${t.amount ?? ''}" required></div>` +
    (isExp ? `<div class="field"><label for="entryCat">Category</label><select id="entryCat">${CATS.map(c => `<option value="${esc(c[0])}" ${t.category === c[0] ? 'selected' : ''}>${c[1]} ${c[0]}</option>`).join('')}</select></div>`
      : (goalSel.length ? `<div class="field"><label for="entryGoal">Allocate to a goal (optional)</label><select id="entryGoal"><option value="">General savings</option>${goalSel.map(g => `<option value="${g.id}" ${(t.goalId ?? presetGoal) === g.id ? 'selected' : ''}>${esc(g.emoji)} ${esc(g.name)}</option>`).join('')}</select></div>` : '')) +
    `<div class="field"><label for="entryDate">Date</label><input id="entryDate" type="date" value="${defDate}" max="${today()}" required></div><div class="field"><label for="entryNote">Note (optional)</label><input id="entryNote" maxlength="120" placeholder="e.g. Lunch with friends" value="${esc(t.note || '')}"></div>`;
  modal(tx ? (isExp ? 'Edit expense' : 'Edit savings entry') : (isExp ? 'Add an expense' : 'Add money to savings'), body, async () => {
    const amount = Number($('entryAmount').value), date = $('entryDate').value;
    if (!amount || amount <= 0 || !date) fail('Enter a valid amount and date.');
    if (date > today()) fail('Dates in the future are not allowed.');
    const payload = { type, amount, date, note: $('entryNote').value.trim(), category: isExp ? $('entryCat').value : 'Savings', goalId: !isExp && $('entryGoal') ? $('entryGoal').value || null : null };
    const d = await api(tx ? '/api/transactions/' + tx.id : '/api/transactions', { method: tx ? 'PUT' : 'POST', body: payload });
    closeModal(); apply(d);
    toast(tx ? 'Entry updated!' : isExp ? 'Expense added!' : 'Savings updated!');
    if (!tx && monthOf(date) !== state.currentMonth) toast(`Saved to ${monthName(monthOf(date))}.`);
  }, { saveText: tx ? 'Save changes' : 'Save' });
}
$('addExpenseBtn').onclick = () => entryModal('expense'); $('addSavingBtn').onclick = () => entryModal('saving');
$('fab').onclick = () => entryModal('expense');
$('incomeBtn').onclick = () => {
  const s = state.summary, isCur = state.month === state.currentMonth;
  modal('Update monthly allowance', `<div class="field"><label for="allowanceInput">Allowance for ${monthName(state.month)} (₹)</label><input id="allowanceInput" type="number" min="0" step="1" inputmode="numeric" value="${s.allowance}"></div>${isCur ? '' : '<label style="display:flex;gap:8px;font-size:13px;align-items:center"><input type="checkbox" id="makeDefault"> Also use as my default for new months</label>'}<p class="muted" style="font-size:12px">Carried-forward money (${money(s.carry)}) is added separately and will not be changed.${isCur ? ' This also becomes your default for future months.' : ''}</p>`, async () => {
    const n = Number($('allowanceInput').value);
    if ($('allowanceInput').value === '' || n < 0 || !Number.isFinite(n)) fail('Enter a valid allowance.');
    apply(await api('/api/months/' + state.month, { method: 'PUT', body: { allowance: n, makeDefault: $('makeDefault')?.checked } }));
    closeModal(); toast('Allowance updated!');
  });
};
function goalModal(goal) {
  const g = goal || {}; let emoji = g.emoji || '🎯';
  const minDate = localDate(new Date(Date.now() + 864e5));
  modal(goal ? 'Edit savings goal' : 'Create a savings goal', `<div class="field"><label for="goalName">What are you saving for?</label><input id="goalName" maxlength="60" placeholder="e.g. New laptop" value="${esc(g.name || '')}" required></div>
    <div class="field"><label>Pick an icon</label><div class="emoji-pick" id="emojiPick">${GOAL_EMOJIS.map(e => `<button type="button" data-emoji="${e}" class="${e === emoji ? 'sel' : ''}">${e}</button>`).join('')}</div></div>
    <div class="field"><label for="goalTarget">Target amount (₹)</label><input id="goalTarget" type="number" min="1" step="1" inputmode="numeric" placeholder="e.g. 40000" value="${g.target ?? ''}" required></div>
    <div class="field"><label for="goalDeadline">Target date (optional)</label><input id="goalDeadline" type="date" min="${minDate}" value="${g.deadline || ''}"><span class="hint">We'll calculate how much to save per day and per month.</span></div>`, async () => {
    const name = $('goalName').value.trim(), target = Number($('goalTarget').value);
    if (!name || !(target > 0)) fail('Add a goal name and valid target.');
    apply(await api(goal ? '/api/goals/' + goal.id : '/api/goals', { method: goal ? 'PUT' : 'POST', body: { name, target, emoji, deadline: $('goalDeadline').value || null } }));
    closeModal(); toast(goal ? 'Goal updated!' : 'Goal created! 🎯');
  });
  $('emojiPick').onclick = e => { const b = e.target.closest('[data-emoji]'); if (!b) return; emoji = b.dataset.emoji; $('emojiPick').querySelectorAll('button').forEach(x => x.classList.toggle('sel', x === b)); };
}
$('goalBtn').onclick = () => goalModal(); $('goalBtn2').onclick = () => goalModal();
$('challengeBtn').onclick = () => busy($('challengeBtn'), async () => { apply(await api('/api/challenge', { method: 'POST' })); toast('Challenge accepted! Try a no-spend day.'); });

document.addEventListener('click', async e => {
  const b = e.target.closest('[data-action]'); if (!b) return;
  const id = Number(b.dataset.id), act = b.dataset.action;
  if (act === 'edit-tx') { const t = state.transactions.find(x => x.id === id); if (t) entryModal(t.type, t); }
  if (act === 'delete-tx') { if (await confirmBox('Delete this record?', 'This entry will be removed and your balances recalculated.')) busy(null, async () => { apply(await api('/api/transactions/' + id, { method: 'DELETE' })); toast('Entry deleted.'); }); }
  if (act === 'contribute') entryModal('saving', null, id);
  if (act === 'edit-goal') goalModal(state.goals.find(g => g.id === id));
  if (act === 'delete-goal') { if (await confirmBox('Delete this goal?', 'Money already saved stays in your savings history as general savings.')) busy(null, async () => { apply(await api('/api/goals/' + id, { method: 'DELETE' })); toast('Goal deleted.'); }); }
});

// ------------------------------------------------------------------ EXPORT / PRINT / SETTINGS
function download(month) { const a = document.createElement('a'); a.href = '/api/export.csv?month=' + encodeURIComponent(month); a.download = `StudentSpend-${month}.csv`; document.body.appendChild(a); a.click(); a.remove(); }
$('exportBtn').onclick = () => download(state.month); $('exportMonthBtn').onclick = () => download(state.month); $('exportAllBtn').onclick = () => download('all');
$('printBtn').onclick = () => window.print();
function setTheme(t) { document.documentElement.setAttribute('data-theme', t); try { localStorage.setItem('ss_theme', t); } catch (e) { /* ignore */ } $('themeBtn').textContent = t === 'dark' ? '☀️' : '🌙'; if (state) render(); }
$('themeBtn').onclick = () => setTheme(document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
$('darkToggle').onclick = $('themeBtn').onclick;
$('profileForm').onsubmit = e => { e.preventDefault(); busy(e.submitter, async () => { const r = await api('/api/profile', { method: 'PUT', body: { name: $('profileName').value } }); state.user = r.user; render(); toast('Profile saved!'); }); };
$('limitsForm').onsubmit = e => { e.preventDefault(); const limits = {}; $('limitFields').querySelectorAll('input').forEach(i => { limits[i.dataset.cat] = i.value === '' ? null : Number(i.value); }); busy(e.submitter, async () => { apply(await api('/api/limits', { method: 'PUT', body: { limits, month: state.month } })); toast('Spending limits saved!'); }); };
$('passwordForm').onsubmit = e => { e.preventDefault(); busy(e.submitter, async () => { await api('/api/password', { method: 'POST', body: { current: $('curPw').value, new: $('newPw').value } }); $('passwordForm').reset(); toast('Password updated!'); }); };
$('deleteAccountBtn').onclick = () => modal('Delete your account?', '<div class="field"><label for="delPw">Confirm with your password</label><input id="delPw" type="password" autocomplete="current-password" required></div>', async () => {
  await api('/api/account', { method: 'DELETE', body: { password: $('delPw').value } }); closeModal(); await loadSession(); showAuth(); auth(false); location.hash = ''; toast('Your account has been deleted.');
}, { saveText: 'Delete forever', sub: 'This permanently removes all your transactions, goals and settings.', danger: true });

// Rollover at midnight / when returning to the tab on a new day
let lastDay = today();
setInterval(() => { if (state && today() !== lastDay) { lastDay = today(); refresh(); } }, 60000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && state && today() !== lastDay) { lastDay = today(); refresh(); } });

// ------------------------------------------------------------------ BOOT
(async () => {
  setTheme(document.documentElement.getAttribute('data-theme') || 'light');
  auth(false);
  try {
    const s = await loadSession();
    if (s.authenticated) await openApp(); else showAuth();
  } catch (e) { showAuth(); toast('Could not reach the server. Please try again.'); }
})();
