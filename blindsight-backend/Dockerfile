# ── Stage 1: dependencies ──────────────────────────────────────────────────────
FROM python:3.12.3-slim AS deps

WORKDIR /app

# System libs needed by aiortc / av / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev libopus-dev libvpx-dev \
    ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.12.3-slim AS runner

WORKDIR /app

# Runtime system libs only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopus0 libvpx9 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application source
COPY . .

# Non-root user for security
RUN useradd -m -u 1001 agent && chown -R agent:agent /app
USER agent

# Call type and call ID configurable via env with sane defaults
ENV CALL_TYPE=default
ENV CALL_ID=blindsight-live
ENV LOG_LEVEL=INFO

CMD ["sh", "-c", "python main.py --call-type $CALL_TYPE --call-id $CALL_ID --log-level $LOG_LEVEL"]
