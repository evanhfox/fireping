ARG PY_VERSION=3.11

# Builder stage (Alpine)
FROM python:${PY_VERSION}-alpine AS builder
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VENV_PATH=/opt/venv
RUN python -m venv "$VENV_PATH"
ENV PATH="$VENV_PATH/bin:$PATH"
WORKDIR /app
RUN apk add --no-cache ca-certificates
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# Runtime stage (Alpine, non-root)
FROM python:${PY_VERSION}-alpine
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
RUN apk add --no-cache ca-certificates && \
    addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/app /app/app
ENV HOST=0.0.0.0 PORT=8080
EXPOSE 8080
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
