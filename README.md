## NetProbe (fireping)

Lightweight network probing and visualization service built with FastAPI. It continuously measures TCP connect latency, DNS lookup latency, and HTTP request performance, stores samples in SQLite, computes minute rollups, and exposes a minimal web UI with live charts plus a JSON API.

### Features

- **Probes**: TCP connect, DNS resolve, HTTP request
- **Live stream**: Server-Sent Events for real-time updates
- **Storage**: Async SQLite via SQLAlchemy with simple rollups every minute
- **Metrics**: Recent sample feed and historical rollups (p50/p95/avg and success rate)
- **Config API**: In-memory jobs/targets you can add/remove at runtime
- **Auth**: Optional Basic Auth for API routes (disabled by default unless password set)
- **UI**: Single-page dashboard (Tailwind + Chart.js) served from `app/static/`

### Repository layout

- `app/main.py`: FastAPI app, lifespan tasks, middleware, static files
- `app/routers/`: API routers
  - `ping.py` (TCP), `dns.py`, `http_probe.py`, `metrics.py`, `config.py`, `stream.py`
- `app/services/`: background scheduler and rollup maintenance
- `app/db/`: SQLAlchemy models and async repo helpers
- `app/utils/`: in-memory event bus and ring buffer
- `app/static/`: dashboard UI (`index.html`, `app.js`)
- `Dockerfile`, `systemd/netprobe.service`, `requirements.txt`

### Quick start (local)

Prereqs: Python 3.11+, `pip`

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: set a Basic Auth password for API endpoints
export ADMIN_PASSWORD=changeme

# Optional: choose DB file (defaults to ./data/app.db)
export DATABASE_FILE=data/app.db

uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open the dashboard: `http://localhost:8080/`

Health check: `GET /healthz`

### Docker

Build and run:

```bash
docker build -t netprobe .
docker run --rm -p 8080:8080 \
  -e ADMIN_PASSWORD=changeme \
  -e DATABASE_FILE=/data/app.db \
  -v $(pwd)/data:/data \
  netprobe
```

### Systemd (example)

An example unit is provided at `systemd/netprobe.service`. Create `/etc/netprobe.env` with:

```ini
ADMIN_PASSWORD=changeme
# DATABASE_URL can override SQLite, e.g. postgres+asyncpg://user:pass@host/db
# DATABASE_FILE=/var/lib/netprobe/app.db
```

Adjust `WorkingDirectory`, user/group, and paths as needed, then:

```bash
sudo cp -r /path/to/repo /opt/netprobe
sudo useradd -r -s /usr/sbin/nologin netprobe || true
sudo chown -R netprobe:netprobe /opt/netprobe
sudo cp systemd/netprobe.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now netprobe
```

### Configuration model

Jobs/targets are kept in-memory and editable via the Config API. On startup, sensible defaults are used. When config `version` changes, the scheduler restarts per-job workers.

Default sets include:

- TCP: `1.1.1.1:443`, `8.8.8.8:443`, `google.com:443`
- DNS: `google.com` and `cloudflare.com` via resolvers `1.1.1.1`, `8.8.8.8`
- HTTP: `https://www.google.com` and `https://www.cloudflare.com`

### Environment variables

- `ADMIN_USER` (default: `admin`)
- `ADMIN_PASSWORD` (unset = no auth; set to enable Basic Auth for `/api/*`)
- `DATABASE_URL` (optional; overrides SQLite if provided)
- `DATABASE_FILE` (SQLite file path, default `./data/app.db`)
- `HOST`, `PORT` (used in Dockerfile `CMD` but you can override with uvicorn args)

### API overview

Auth: If `ADMIN_PASSWORD` is set, include HTTP Basic credentials. The UI will prompt and send `Authorization` headers automatically.

- `GET /healthz` → `{ ok, version, started }`

- TCP (`/api/ping`)
  - `POST /api/ping/tcp`
    - body: `{ host: string, port?: number=443, timeout_sec?: number=2.0 }`
    - resp: `{ host, port, latency_ms, success, error? }`

- DNS (`/api/dns`)
  - `POST /api/dns/query`
    - body: `{ fqdn: string, record_type?: string="A", resolvers?: string[], timeout_sec?: number=2.0 }`
    - resp: `{ fqdn, record_type, resolver?, latency_ms, rcode?, success, answers: [{ value }] }`

- HTTP (`/api/http`)
  - `POST /api/http/probe`
    - body: `{ url: string, method?: string="GET", timeout_sec?: number=5.0 }`
    - resp: `{ url, method, status_code?, latency_ms, success, error? }`

- Stream (`/api/stream`)
  - `GET /api/stream/events` → text/event-stream of events: `{ type: "tcp_sample"|"dns_sample"|"http_sample", data: {...}, ts }`

- Metrics (`/api/metrics`)
  - `GET /api/metrics/recent?limit=500` → recent in-memory events
  - `GET /api/metrics/summary` → last 10m sample counts from aggregates
  - `GET /api/metrics/tcp_rollup?minutes=60&step_sec=60&host=1.1.1.1` → p50/p95/avg + success_rate by bucket
  - `GET /api/metrics/dns_rollup?minutes=60&step_sec=60&fqdn=example.com` → same structure

- Config (`/api/config`)
  - `GET /api/config/state` → current in-memory config
  - `POST /api/config/tcp` `{ id, host, port, interval_sec }`
  - `DELETE /api/config/tcp/{id}`
  - `POST /api/config/dns` `{ id, fqdn, resolvers?, record_type?, interval_sec }`
  - `DELETE /api/config/dns/{id}`
  - `POST /api/config/http` `{ id, url, method?, interval_sec }`
  - `DELETE /api/config/http/{id}`

### Data model (SQLite)

- Samples: `samples_tcp`, `samples_dns`, `samples_http` with timestamps, success, latency, and metadata
- Aggregates: `aggregates_*_1m` store minute buckets with count/success_count p50/p95/avg/min/max

### Development notes

- The UI lives at `/` and talks to the same-origin API
- The scheduler and rollup maintenance run in background tasks started in app lifespan
- SSE stream includes a replay of recent events and then live updates

### License

MIT or similar; update as appropriate for your project.


