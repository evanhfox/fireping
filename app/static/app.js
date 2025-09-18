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
      { label: 'TCP (ms)', data: [], borderColor: '#60a5fa', tension: 0.2 },
      { label: 'DNS (ms)', data: [], borderColor: '#f472b6', tension: 0.2 },
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

