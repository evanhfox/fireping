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

