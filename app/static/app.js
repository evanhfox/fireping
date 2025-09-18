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
      { label: 'TCP (ms)', data: [], borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.15)', tension: 0.25, pointRadius: 0, fill: true },
      { label: 'DNS (ms)', data: [], borderColor: '#db2777', backgroundColor: 'rgba(219,39,119,0.15)', tension: 0.25, pointRadius: 0, fill: true },
      { label: 'HTTP (ms)', data: [], borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,0.15)', tension: 0.25, pointRadius: 0, fill: true },
    ],
  },
  options: {
    responsive: true,
    animation: false,
    plugins: { legend: { labels: { color: '#525252' } } },
    scales: {
      x: { ticks: { color: '#6b7280' }, grid: { color: '#e5e7eb' } },
      y: { min: 0, suggestedMax: 1000, ticks: { color: '#6b7280' }, grid: { color: '#e5e7eb' } },
    },
  },
});

const hctx = document.getElementById('historyChart');
const historyChart = new Chart(hctx, {
  type: 'line',
  data: { labels: [], datasets: [
    { label: 'p50', data: [], borderColor: '#2563eb', tension: 0.25 },
    { label: 'p95', data: [], borderColor: '#f59e0b', tension: 0.25 },
    { label: 'avg', data: [], borderColor: '#7c3aed', tension: 0.25 },
    { label: 'success %', data: [], borderColor: '#16a34a', tension: 0.25, yAxisID: 'y1' },
  ]},
  options: {
    responsive: true,
    animation: false,
    plugins: { legend: { labels: { color: '#525252' } } },
    scales: {
      x: { ticks: { color: '#6b7280' }, grid: { color: '#e5e7eb' } },
      y: { ticks: { color: '#6b7280' }, grid: { color: '#e5e7eb' } },
      y1: { position: 'right', min: 0, max: 1, ticks: { color: '#6b7280' }, grid: { drawOnChartArea: false } },
    },
  },
});

function formatTimeEastern(input) {
  const d = typeof input === 'string' ? new Date(input) : input;
  return d.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });
}

function upsertCard(key, payload) {
  // Sanitize key for use in DOM ids (avoid spaces, slashes, colons, etc.)
  const safeKey = key.replace(/[^a-zA-Z0-9_-]/g, '_');
  const cards = document.getElementById('cards');
  if (!state.cards.has(safeKey)) {
    const div = document.createElement('div');
    div.className = 'bg-white rounded-xl p-4 border border-neutral-200 shadow-sm';
    div.innerHTML = `<div class="text-sm text-neutral-400">${key}</div><div class="text-2xl font-semibold" id="val-${safeKey}">—</div><div class="text-xs text-neutral-400" id="meta-${safeKey}"></div>`;
    cards.appendChild(div);
    state.cards.set(safeKey, div);
  }
  const div = state.cards.get(safeKey);
  const val = div.querySelector(`#val-${safeKey}`);
  const meta = div.querySelector(`#meta-${safeKey}`);
  val.textContent = `${Math.round(payload.latency_ms)} ms`;
  const ok = payload.success;
  meta.textContent = ok ? 'ok' : (payload.rcode || payload.error || 'error');
  val.className = `text-2xl font-semibold ${ok ? 'text-green-600' : 'text-red-600'}`;
}

function pushPoint(seriesIndex, label, value) {
  // Add a new label and pad all datasets with null to keep lengths aligned
  state.labels.push(label);
  chart.data.labels = state.labels;
  chart.data.datasets.forEach(d => d.data.push(null));

  const lastIdx = state.labels.length - 1;
  const num = Number(value);
  if (Number.isFinite(num)) {
    chart.data.datasets[seriesIndex].data[lastIdx] = num;
  }

  const maxPoints = 300;
  if (state.labels.length > maxPoints) {
    state.labels.shift();
    chart.data.datasets.forEach(d => d.data.shift());
  }
  // Dynamically adapt Y scale to current data range
  const allValues = chart.data.datasets.flatMap(d => d.data).filter(v => Number.isFinite(v));
  const curMax = allValues.length ? Math.max(...allValues) : 1000;
  chart.options.scales.y.suggestedMax = Math.max(100, Math.ceil(curMax * 1.2));
  chart.update('none');
}

function handleEvent(evt) {
  let obj;
  try {
    obj = JSON.parse(evt.data);
  } catch { return; }
  const { type, data, ts } = obj;
  const label = formatTimeEastern(ts || new Date().toISOString());
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
    const res = await apiFetch('/api/metrics/recent?limit=200');
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

  await refreshSummary();
  // Summary every 30s
  setInterval(refreshSummary, 30000);

  // Auto-run history now and every 60s
  await runHistory();
  setInterval(runHistory, 60000);

  wireSummaryClicks();
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
    const res = await apiFetch(url);
    if (!res.ok) return;
    const json = await res.json();
    const labels = json.points.map(p => formatTimeEastern(new Date(p.bucket)));
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
  // Legacy settings panel may not exist; guard DOM lookups
  const tcpList = document.getElementById('tcp-list');
  const dnsList = document.getElementById('dns-list');
  const httpList = document.getElementById('http-list');
  if (!tcpList && !dnsList && !httpList) return;

  const res = await apiFetch('/api/config/state');
  if (!res.ok) return;
  const cfg = await res.json();

  if (tcpList) {
    tcpList.innerHTML = '';
    for (const t of cfg.tcp) {
      const el = document.createElement('div');
      el.className = 'flex justify-between items-center bg-neutral-800 rounded px-2 py-1';
      el.innerHTML = `<span>${t.host}:${t.port} (${t.interval_sec}s)</span><button data-id="${t.id}" class="tcp-del text-red-400">Delete</button>`;
      tcpList.appendChild(el);
    }
  }
  if (dnsList) {
    dnsList.innerHTML = '';
    for (const d of cfg.dns) {
      const el = document.createElement('div');
      el.className = 'flex justify-between items-center bg-neutral-800 rounded px-2 py-1';
      el.innerHTML = `<span>${d.fqdn} (${d.interval_sec}s)</span><button data-id="${d.id}" class="dns-del text-red-400">Delete</button>`;
      dnsList.appendChild(el);
    }
  }
  if (httpList) {
    httpList.innerHTML = '';
    // HTTP jobs displayed only if present; managed via config API once added server-side in future
  }
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

document.getElementById('tcp-add')?.addEventListener('click', addTcp);
document.getElementById('dns-add')?.addEventListener('click', addDns);
document.getElementById('tcp-list')?.addEventListener('click', async (e) => {
  const btn = e.target.closest('.tcp-del');
  if (!btn) return;
  const id = btn.getAttribute('data-id');
  await apiFetch(`/api/config/tcp/${encodeURIComponent(id)}`, { method: 'DELETE' });
  await refreshConfig();
});
document.getElementById('dns-list')?.addEventListener('click', async (e) => {
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

document.getElementById('http-add')?.addEventListener('click', addHttp);

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  return res;
}

async function refreshSummary() {
  try {
    const r = await apiFetch('/api/metrics/summary');
    if (!r.ok) return;
    const s = await r.json();
    document.getElementById('sum-tcp').textContent = s.last_10m_samples.tcp;
    document.getElementById('sum-dns').textContent = s.last_10m_samples.dns;
    document.getElementById('sum-http').textContent = s.last_10m_samples.http;
  } catch {}
}

function wireSummaryClicks() {
  const sumTcp = document.getElementById('sum-tcp');
  const sumDns = document.getElementById('sum-dns');
  if (sumTcp && sumTcp.parentElement) {
    sumTcp.parentElement.classList.add('cursor-pointer');
    sumTcp.parentElement.addEventListener('click', async () => {
      document.getElementById('hist-kind').value = 'tcp';
      updateFilterVisibility();
      await runHistory();
    });
  }
  if (sumDns && sumDns.parentElement) {
    sumDns.parentElement.classList.add('cursor-pointer');
    sumDns.parentElement.addEventListener('click', async () => {
      document.getElementById('hist-kind').value = 'dns';
      updateFilterVisibility();
      await runHistory();
    });
  }
}

refreshConfig();

// Manage Probes modal logic
function ensureManageModal() {
  let modal = document.getElementById('manage-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'manage-modal';
    modal.className = 'hidden fixed inset-0 z-[9999]';
    modal.innerHTML = `
      <div class="absolute inset-0 bg-black/30"></div>
      <div class="relative mx-auto mt-12 w-[min(100%,900px)] bg-white rounded-xl shadow-xl border border-neutral-200">
        <div class="flex items-center justify-between px-4 py-3 border-b border-neutral-200">
          <h3 class="text-lg font-medium">Manage Probes</h3>
          <button id="close-manage" class="text-neutral-500 hover:text-neutral-700">✕</button>
        </div>
        <div class="px-4 pt-3">
          <div class="flex gap-2 mb-3">
            <button data-tab="tcp" class="tab active bg-rose-600 hover:bg-rose-500 text-white rounded px-3 py-1">TCP</button>
            <button data-tab="dns" class="tab bg-neutral-100 hover:bg-neutral-200 rounded px-3 py-1 border border-neutral-300">DNS</button>
            <button data-tab="http" class="tab bg-neutral-100 hover:bg-neutral-200 rounded px-3 py-1 border border-neutral-300">HTTP</button>
          </div>
          <div id="tab-tcp" class="tab-pane space-y-3">
            <div class="flex gap-2">
              <input id="m-tcp-host" placeholder="host" class="bg-neutral-100 rounded px-2 py-1 w-full border border-neutral-300" />
              <input id="m-tcp-port" type="number" placeholder="port" class="bg-neutral-100 rounded px-2 py-1 w-24 border border-neutral-300" />
              <input id="m-tcp-interval" type="number" step="0.5" placeholder="interval (s)" class="bg-neutral-100 rounded px-2 py-1 w-32 border border-neutral-300" />
              <button id="m-tcp-add" class="bg-rose-600 hover:bg-rose-500 text-white rounded px-3 py-1">Add</button>
            </div>
            <div id="m-tcp-list" class="divide-y divide-neutral-200"></div>
          </div>
          <div id="tab-dns" class="tab-pane hidden space-y-3">
            <div class="flex gap-2">
              <input id="m-dns-fqdn" placeholder="fqdn" class="bg-neutral-100 rounded px-2 py-1 w-full border border-neutral-300" />
              <input id="m-dns-resolvers" placeholder="resolvers (comma)" class="bg-neutral-100 rounded px-2 py-1 w-full border border-neutral-300" />
              <input id="m-dns-interval" type="number" step="0.5" placeholder="interval (s)" class="bg-neutral-100 rounded px-2 py-1 w-32 border border-neutral-300" />
              <button id="m-dns-add" class="bg-rose-600 hover:bg-rose-500 text-white rounded px-3 py-1">Add</button>
            </div>
            <div id="m-dns-list" class="divide-y divide-neutral-200"></div>
          </div>
          <div id="tab-http" class="tab-pane hidden space-y-3">
            <div class="flex gap-2">
              <input id="m-http-url" placeholder="https://..." class="bg-neutral-100 rounded px-2 py-1 w-full border border-neutral-300" />
              <select id="m-http-method" class="bg-neutral-100 rounded px-2 py-1 w-28 border border-neutral-300"><option>GET</option><option>HEAD</option></select>
              <input id="m-http-interval" type="number" step="0.5" placeholder="interval (s)" class="bg-neutral-100 rounded px-2 py-1 w-32 border border-neutral-300" />
              <button id="m-http-add" class="bg-rose-600 hover:bg-rose-500 text-white rounded px-3 py-1">Add</button>
            </div>
            <div id="m-http-list" class="divide-y divide-neutral-200"></div>
          </div>
          <div class="h-4"></div>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
  return modal;
}

let manageModal = null;
function showModal() {
  manageModal = document.getElementById('manage-modal') || ensureManageModal();
  manageModal.classList.remove('hidden');
  activateTab('tcp');
  renderManageLists();
}
function hideModal() { (manageModal || ensureManageModal()).classList.add('hidden'); }

// Bind interactions after page load
window.addEventListener('DOMContentLoaded', () => {
  const openBtn = document.getElementById('open-manage');
  openBtn?.addEventListener('click', (e) => { e.preventDefault(); showModal(); });
});

// Delegated clicks for dynamic modal content
document.body.addEventListener('click', (e) => {
  const target = e.target;
  if (!(target instanceof Element)) return;
  if (target.id === 'close-manage') { hideModal(); }
  if (target.matches('.tab')) { const name = target.getAttribute('data-tab'); activateTab(name); }
  if (manageModal && target === manageModal) { hideModal(); }
});

function activateTab(name) {
  const tabs = document.querySelectorAll('.tab');
  const panes = document.querySelectorAll('.tab-pane');
  tabs.forEach(btn => {
    const isActive = btn.getAttribute('data-tab') === name;
    btn.classList.toggle('active', isActive);
    if (isActive) {
      btn.classList.remove('bg-neutral-100', 'hover:bg-neutral-200', 'border', 'border-neutral-300');
      btn.classList.add('bg-rose-600', 'hover:bg-rose-500', 'text-white');
    } else {
      btn.classList.remove('bg-rose-600', 'hover:bg-rose-500', 'text-white');
      btn.classList.add('bg-neutral-100', 'hover:bg-neutral-200', 'border', 'border-neutral-300');
    }
  });
  panes.forEach(p => {
    p.classList.toggle('hidden', p.id !== `tab-${name}`);
  });
}
document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => activateTab(b.getAttribute('data-tab'))));

async function renderManageLists() {
  try {
    const res = await apiFetch('/api/config/state');
    if (!res.ok) return;
    const cfg = await res.json();
    const tcp = document.getElementById('m-tcp-list');
    tcp.innerHTML = '';
    for (const t of cfg.tcp) {
      const row = document.createElement('div');
      row.className = 'flex items-center justify-between py-2';
      row.innerHTML = `<div class="text-sm">${t.host}:${t.port} <span class="text-neutral-400">(${t.interval_sec}s)</span></div>
      <div class="flex gap-2">
        <button data-id="${t.id}" data-kind="tcp" class="m-edit text-blue-400">Edit</button>
        <button data-id="${t.id}" data-kind="tcp" class="m-del text-red-400">Delete</button>
      </div>`;
      tcp.appendChild(row);
    }
    const dns = document.getElementById('m-dns-list');
    dns.innerHTML = '';
    for (const d of cfg.dns) {
      const row = document.createElement('div');
      row.className = 'flex items-center justify-between py-2';
      row.innerHTML = `<div class="text-sm">${d.fqdn} <span class="text-neutral-400">(${d.interval_sec}s)</span></div>
      <div class="flex gap-2">
        <button data-id="${d.id}" data-kind="dns" class="m-edit text-blue-400">Edit</button>
        <button data-id="${d.id}" data-kind="dns" class="m-del text-red-400">Delete</button>
      </div>`;
      dns.appendChild(row);
    }
    const http = document.getElementById('m-http-list');
    http.innerHTML = '';
    for (const h of (cfg.http || [])) {
      const row = document.createElement('div');
      row.className = 'flex items-center justify-between py-2';
      row.innerHTML = `<div class="text-sm">${h.method} ${h.url} <span class="text-neutral-400">(${h.interval_sec}s)</span></div>
      <div class="flex gap-2">
        <button data-id="${h.id}" data-kind="http" class="m-edit text-blue-400">Edit</button>
        <button data-id="${h.id}" data-kind="http" class="m-del text-red-400">Delete</button>
      </div>`;
      http.appendChild(row);
    }
  } catch {}
}

async function addTcpModal() {
  const host = document.getElementById('m-tcp-host').value.trim();
  const port = parseInt(document.getElementById('m-tcp-port').value, 10) || 443;
  const interval = parseFloat(document.getElementById('m-tcp-interval').value) || 5.0;
  if (!host) return;
  const id = `tcp-${host}-${port}-${Date.now()}`;
  await apiFetch('/api/config/tcp', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, host, port, interval_sec: interval }) });
  await renderManageLists();
}
document.getElementById('m-tcp-add')?.addEventListener('click', addTcpModal);

async function addDnsModal() {
  const fqdn = document.getElementById('m-dns-fqdn').value.trim();
  const resolvers = document.getElementById('m-dns-resolvers').value.trim().split(',').map(s => s.trim()).filter(Boolean);
  const interval = parseFloat(document.getElementById('m-dns-interval').value) || 5.0;
  if (!fqdn) return;
  const id = `dns-${fqdn}-${Date.now()}`;
  await apiFetch('/api/config/dns', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, fqdn, resolvers, interval_sec: interval }) });
  await renderManageLists();
}
document.getElementById('m-dns-add')?.addEventListener('click', addDnsModal);

async function addHttpModal() {
  const url = document.getElementById('m-http-url').value.trim();
  const method = document.getElementById('m-http-method').value;
  const interval = parseFloat(document.getElementById('m-http-interval').value) || 10.0;
  if (!url) return;
  const id = `http-${Date.now()}`;
  await apiFetch('/api/config/http', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, url, method, interval_sec: interval }) });
  await renderManageLists();
}
document.getElementById('m-http-add')?.addEventListener('click', addHttpModal);

// Delete handlers
function openEditDialog(kind, item) {
  const value = prompt(`Edit ${kind} (JSON)`, JSON.stringify(item));
  if (!value) return null;
  try { return JSON.parse(value); } catch { alert('Invalid JSON'); return null; }
}

document.body.addEventListener('click', async (e) => {
  const del = e.target.closest('.m-del');
  const edit = e.target.closest('.m-edit');
  if (del) {
    const id = del.getAttribute('data-id');
    const kind = del.getAttribute('data-kind');
    const path = kind === 'tcp' ? 'tcp' : kind === 'dns' ? 'dns' : 'http';
    await apiFetch(`/api/config/${path}/${encodeURIComponent(id)}`, { method: 'DELETE' });
    await renderManageLists();
  } else if (edit) {
    const id = edit.getAttribute('data-id');
    const kind = edit.getAttribute('data-kind');
    // Fetch current state to find the item
    const res = await apiFetch('/api/config/state');
    if (!res.ok) return;
    const cfg = await res.json();
    let item = (kind === 'tcp' ? cfg.tcp : kind === 'dns' ? cfg.dns : cfg.http).find(x => x.id === id);
    const updated = openEditDialog(kind, item);
    if (!updated) return;
    // For simplicity: delete then re-add with same id
    const path = kind === 'tcp' ? 'tcp' : kind === 'dns' ? 'dns' : 'http';
    await apiFetch(`/api/config/${path}/${encodeURIComponent(id)}`, { method: 'DELETE' });
    await apiFetch(`/api/config/${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updated) });
    await renderManageLists();
  }
});

