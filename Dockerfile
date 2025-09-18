ARG PY_VERSION=3.11

# Builder: install deps into a venv
FROM python:${PY_VERSION}-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VENV_PATH=/opt/venv
RUN python -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Runtime: distroless to minimize OS CVEs
FROM gcr.io/distroless/python3-debian12:${PY_VERSION}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:/usr/local/bin:/usr/bin:/bin"
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/app /app/app
ENV HOST=0.0.0.0 PORT=8080
EXPOSE 8080
CMD ["/opt/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
