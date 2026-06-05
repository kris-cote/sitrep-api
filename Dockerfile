FROM python:3.12-slim-bookworm

WORKDIR /app

# Keep this minimal; certs are required for outbound HTTPS.
RUN set -eux; \
  apt-get update -o Acquire::ForceIPv4=true -o Acquire::Retries=3 -o Acquire::http::Timeout=10 -o Acquire::https::Timeout=10 -o Acquire::http::Pipeline-Depth=0; \
  apt-get install -y --no-install-recommends ca-certificates; \
  rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY db /app/db

EXPOSE 9000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000}"]
