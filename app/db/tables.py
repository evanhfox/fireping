from sqlalchemy import (
    MetaData, Table, Column, Integer, String, Float, Boolean, DateTime, Text, JSON, Index
)


metadata = MetaData()


targets_tcp = Table(
    "targets_tcp",
    metadata,
    Column("id", String, primary_key=True),
    Column("host", String, nullable=False),
    Column("port", Integer, nullable=False, default=443),
    Column("interval_sec", Float, nullable=False, default=5.0),
)


jobs_dns = Table(
    "jobs_dns",
    metadata,
    Column("id", String, primary_key=True),
    Column("fqdn", String, nullable=False),
    Column("record_type", String, nullable=False, default="A"),
    Column("resolvers", Text, nullable=True),  # comma-separated for simplicity
    Column("interval_sec", Float, nullable=False, default=5.0),
)


jobs_http = Table(
    "jobs_http",
    metadata,
    Column("id", String, primary_key=True),
    Column("url", String, nullable=False),
    Column("method", String, nullable=False, default="GET"),
    Column("interval_sec", Float, nullable=False, default=5.0),
)


samples_tcp = Table(
    "samples_tcp",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime, nullable=False),
    Column("target_id", String, nullable=True),
    Column("host", String, nullable=False),
    Column("port", Integer, nullable=False),
    Column("latency_ms", Float, nullable=False),
    Column("success", Boolean, nullable=False),
    Index("idx_tcp_ts", "ts"),
)


samples_dns = Table(
    "samples_dns",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime, nullable=False),
    Column("job_id", String, nullable=True),
    Column("fqdn", String, nullable=False),
    Column("record_type", String, nullable=False),
    Column("resolver", String, nullable=True),
    Column("latency_ms", Float, nullable=False),
    Column("rcode", String, nullable=True),
    Column("success", Boolean, nullable=False),
    Index("idx_dns_ts", "ts"),
)


samples_http = Table(
    "samples_http",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", DateTime, nullable=False),
    Column("job_id", String, nullable=True),
    Column("url", String, nullable=False),
    Column("method", String, nullable=False),
    Column("status_code", Integer, nullable=True),
    Column("latency_ms", Float, nullable=False),
    Column("success", Boolean, nullable=False),
    Column("error", String, nullable=True),
    Index("idx_http_ts", "ts"),
)


# Aggregate tables (1-minute buckets)
aggregates_tcp_1m = Table(
    "aggregates_tcp_1m",
    metadata,
    Column("bucket", DateTime, primary_key=True),
    Column("host", String, primary_key=True),
    Column("port", Integer, primary_key=True),
    Column("count", Integer, nullable=False),
    Column("success_count", Integer, nullable=False),
    Column("p50", Float, nullable=True),
    Column("p95", Float, nullable=True),
    Column("avg", Float, nullable=True),
    Column("min", Float, nullable=True),
    Column("max", Float, nullable=True),
)


aggregates_dns_1m = Table(
    "aggregates_dns_1m",
    metadata,
    Column("bucket", DateTime, primary_key=True),
    Column("fqdn", String, primary_key=True),
    Column("resolver", String, primary_key=True),
    Column("count", Integer, nullable=False),
    Column("success_count", Integer, nullable=False),
    Column("p50", Float, nullable=True),
    Column("p95", Float, nullable=True),
    Column("avg", Float, nullable=True),
    Column("min", Float, nullable=True),
    Column("max", Float, nullable=True),
)


aggregates_http_1m = Table(
    "aggregates_http_1m",
    metadata,
    Column("bucket", DateTime, primary_key=True),
    Column("url", String, primary_key=True),
    Column("method", String, primary_key=True),
    Column("count", Integer, nullable=False),
    Column("success_count", Integer, nullable=False),
    Column("p50", Float, nullable=True),
    Column("p95", Float, nullable=True),
    Column("avg", Float, nullable=True),
    Column("min", Float, nullable=True),
    Column("max", Float, nullable=True),
)

