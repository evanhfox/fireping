const state = {
  series: [],
  labels: [],
  cards: new Map(),
};

const ctx = document.getElementById('latencyChart');
const chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: state.labels,
    datasets: [
      { label: 'TCP (ms)', data: [], borderColor: '#60a5fa', tension: 0.2, pointRadius: 0, segment: { borderColor: ctx => (ctx.p1.parsed.y === 0 ? 'rgba(239,68,68,0.8)' : '#60a5fa') } },
      { label: 'DNS (ms)', data: [], borderColor: '#f472b6', tension: 0.2, pointRadius: 0 },
      { label: 'HTTP (ms)', data: [], borderColor: '#22c55e', tension: 0.2, pointRadius: 0 },
    ],
  },
  options: {
    responsive: true,
    animation: false,
    plugins: { legend: { labels: { color: '#d4d4d8' } } },
    scales: {
      x: { ticks: { color: '#a3a3a3' }, grid: { color: '#262626' } },
      y: { ticks: { color: '#a3a3a3' }, grid: { color: '#262626' } },
    },
  },
});

const hctx = document.getElementById('historyChart');
const historyChart = new Chart(hctx, {
  type: 'line',
  data: { labels: [], datasets: [
    { label: 'p50', data: [], borderColor: '#60a5fa', tension: 0.2 },
    { label: 'p95', data: [], borderColor: '#f59e0b', tension: 0.2 },
    { label: 'avg', data: [], borderColor: '#a78bfa', tension: 0.2 },
    { label: 'success %', data: [], borderColor: '#34d399', tension: 0.2, yAxisID: 'y1' },
  ]},
  options: {
    responsive: true,
    animation: false,
    plugins: { legend: { labels: { color: '#d4d4d8' } } },
    scales: {
      x: { ticks: { color: '#a3a3a3' }, grid: { color: '#262626' } },
      y: { ticks: { color: '#a3a3a3' }, grid: { color: '#262626' } },
      y1: { position: 'right', min: 0, max: 1, ticks: { color: '#a3a3a3' }, grid: { drawOnChartArea: false } },
    },
  },
});

function upsertCard(key, payload) {
  const cards = document.getElementById('cards');
  if (!state.cards.has(key)) {
    const div = document.createElement('div');
    div.className = 'bg-neutral-900 rounded-lg p-4';
    div.innerHTML = `<div class="text-sm text-neutral-400">${key}</div><div class="text-2xl font-semibold" id="val-${key}">—</div><div class="text-xs text-neutral-400" id="meta-${key}"></div>`;
    cards.appendChild(div);
    state.cards.set(key, div);
  }
  const div = state.cards.get(key);
  const val = div.querySelector(`#val-${key}`);
  const meta = div.querySelector(`#meta-${key}`);
  val.textContent = `${Math.round(payload.latency_ms)} ms`;
  const ok = payload.success;
  meta.textContent = ok ? 'ok' : (payload.rcode || payload.error || 'error');
  val.className = `text-2xl font-semibold ${ok ? 'text-green-400' : 'text-red-400'}`;
}

function pushPoint(seriesIndex, label, value) {
  state.labels.push(label);
  chart.data.labels = state.labels;
  chart.data.datasets[seriesIndex].data.push(value);
  const maxPoints = 300;
  if (state.labels.length > maxPoints) {
    state.labels.shift();
    chart.data.datasets.forEach(d => d.data.shift());
  }
  chart.update('none');
}

function handleEvent(evt) {
  let obj;
  try {
    obj = JSON.parse(evt.data);
  } catch { return; }
  const { type, data, ts } = obj;
  const label = (ts || new Date().toISOString()).slice(11,19);
  if (type === 'tcp_sample') {
    upsertCard(`tcp-${data.host}:${data.port}`, data);
    pushPoint(0, label, data.latency_ms);
  } else if (type === 'dns_sample') {
    upsertCard(`dns-${data.fqdn}`, data);
    pushPoint(1, label, data.latency_ms);
  } else if (type === 'http_sample') {
    upsertCard(`http-${data.method} ${data.url}`, data);
    pushPoint(2, label, data.latency_ms);
  }
}

async function bootstrap() {
  // Warm with recent samples
  try {
    const res = await fetch('/api/metrics/recent?limit=200');
    if (res.ok) {
      const json = await res.json();
      for (const item of json.items) {
        handleEvent({ data: JSON.stringify(item) });
      }
    }
  } catch {}

  const es = new EventSource('/api/stream/events');
  es.onmessage = handleEvent;
  es.onerror = () => {
    // Auto-reconnect handled by EventSource; we can log if needed
  };

  // Summary every 30s
  setInterval(async () => {
    try {
      const r = await fetch('/api/metrics/summary');
      if (!r.ok) return;
      const s = await r.json();
      document.getElementById('sum-tcp').textContent = s.last_10m_samples.tcp;
      document.getElementById('sum-dns').textContent = s.last_10m_samples.dns;
      document.getElementById('sum-http').textContent = s.last_10m_samples.http;
    } catch {}
  }, 30000);
}

bootstrap();

function updateFilterVisibility() {
  const kind = document.getElementById('hist-kind').value;
  document.getElementById('hist-filter-host').classList.toggle('hidden', kind !== 'tcp');
  document.getElementById('hist-filter-fqdn').classList.toggle('hidden', kind !== 'dns');
}

async function runHistory() {
  const kind = document.getElementById('hist-kind').value;
  const minutes = parseInt(document.getElementById('hist-min').value, 10);
  const step = parseInt(document.getElementById('hist-step').value, 10);
  const host = document.getElementById('hist-host').value.trim();
  const fqdn = document.getElementById('hist-fqdn').value.trim();
  const params = new URLSearchParams({ minutes: String(minutes), step_sec: String(step) });
  if (kind === 'tcp' && host) params.set('host', host);
  if (kind === 'dns' && fqdn) params.set('fqdn', fqdn);
  const url = kind === 'tcp' ? `/api/metrics/tcp_rollup?${params}` : `/api/metrics/dns_rollup?${params}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const json = await res.json();
    const labels = json.points.map(p => new Date(p.bucket).toLocaleTimeString());
    const p50 = json.points.map(p => p.p50 ?? null);
    const p95 = json.points.map(p => p.p95 ?? null);
    const avg = json.points.map(p => p.avg ?? null);
    const sr = json.points.map(p => p.success_rate ?? 0);
    historyChart.data.labels = labels;
    historyChart.data.datasets[0].data = p50;
    historyChart.data.datasets[1].data = p95;
    historyChart.data.datasets[2].data = avg;
    historyChart.data.datasets[3].data = sr;
    historyChart.update('none');
  } catch {}
}

document.getElementById('hist-kind').addEventListener('change', updateFilterVisibility);
document.getElementById('hist-run').addEventListener('click', runHistory);
updateFilterVisibility();

async function refreshConfig() {
  const res = await apiFetch('/api/config/state');
  if (!res.ok) return;
  const cfg = await res.json();
  const tcpList = document.getElementById('tcp-list');
  tcpList.innerHTML = '';
  for (const t of cfg.tcp) {
    const el = document.createElement('div');
    el.className = 'flex justify-between items-center bg-neutral-800 rounded px-2 py-1';
    el.innerHTML = `<span>${t.host}:${t.port} (${t.interval_sec}s)</span><button data-id="${t.id}" class="tcp-del text-red-400">Delete</button>`;
    tcpList.appendChild(el);
  }
  const dnsList = document.getElementById('dns-list');
  dnsList.innerHTML = '';
  for (const d of cfg.dns) {
    const el = document.createElement('div');
    el.className = 'flex justify-between items-center bg-neutral-800 rounded px-2 py-1';
    el.innerHTML = `<span>${d.fqdn} (${d.interval_sec}s)</span><button data-id="${d.id}" class="dns-del text-red-400">Delete</button>`;
    dnsList.appendChild(el);
  }
  const httpList = document.getElementById('http-list');
  httpList.innerHTML = '';
  // HTTP jobs displayed only if present; managed via config API once added server-side in future
}

async function addTcp() {
  const host = document.getElementById('tcp-host').value.trim();
  const port = parseInt(document.getElementById('tcp-port').value, 10) || 443;
  const interval = parseFloat(document.getElementById('tcp-interval').value) || 5.0;
  if (!host) return;
  const id = `tcp-${host}-${port}-${Date.now()}`;
  await apiFetch('/api/config/tcp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, host, port, interval_sec: interval }) });
  await refreshConfig();
}

async function addDns() {
  const fqdn = document.getElementById('dns-fqdn').value.trim();
  const resolvers = document.getElementById('dns-resolvers').value.trim().split(',').map(s => s.trim()).filter(Boolean);
  const interval = parseFloat(document.getElementById('dns-interval').value) || 5.0;
  if (!fqdn) return;
  const id = `dns-${fqdn}-${Date.now()}`;
  await apiFetch('/api/config/dns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, fqdn, resolvers, interval_sec: interval }) });
  await refreshConfig();
}

document.getElementById('tcp-add').addEventListener('click', addTcp);
document.getElementById('dns-add').addEventListener('click', addDns);
document.getElementById('tcp-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('.tcp-del');
  if (!btn) return;
  const id = btn.getAttribute('data-id');
  await apiFetch(`/api/config/tcp/${encodeURIComponent(id)}`, { method: 'DELETE' });
  await refreshConfig();
});
document.getElementById('dns-list').addEventListener('click', async (e) => {
  const btn = e.target.closest('.dns-del');
  if (!btn) return;
  const id = btn.getAttribute('data-id');
  await apiFetch(`/api/config/dns/${encodeURIComponent(id)}`, { method: 'DELETE' });
  await refreshConfig();
});

async function addHttp() {
  const url = document.getElementById('http-url').value.trim();
  const method = document.getElementById('http-method').value;
  const interval = parseFloat(document.getElementById('http-interval').value) || 10.0;
  if (!url) return;
  const id = `http-${Date.now()}`;
  await apiFetch('/api/config/http', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, url, method, interval_sec: interval }) });
  await refreshConfig();
}

document.getElementById('http-add').addEventListener('click', addHttp);

function apiAuthHeader() {
  const user = 'admin';
  const pw = prompt('Password (for Basic auth):', 'changeme');
  if (!pw) return {};
  const token = btoa(`${user}:${pw}`);
  return { 'Authorization': `Basic ${token}` };
}

async function apiFetch(url, options = {}) {
  const headers = Object.assign({}, options.headers || {}, apiAuthHeader());
  const res = await fetch(url, Object.assign({}, options, { headers }));
  return res;
}

refreshConfig();

