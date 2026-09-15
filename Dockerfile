# syntax=docker/dockerfile:1

# ── Dashboard build ───────────────────────────────────────────
FROM node:22-slim AS dashboard
WORKDIR /dashboard
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build

# ── Agent ─────────────────────────────────────────────────────
FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg renders the final cut. The fonts are the ones render.py looks for on
# Linux: Noto CJK for Korean/Japanese/Chinese, Noto Sans Khmer, DejaVu otherwise.
# libfreetype6, fontconfig, and libfontconfig1 provide drawtext filter support.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ffmpeg \
    libfreetype6 \
    fontconfig \
    libfontconfig1 \
    fonts-noto-cjk \
    fonts-noto-core \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 flowkit

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY agent/ agent/
COPY skills/ skills/
COPY tools/ tools/
COPY --from=dashboard /dashboard/dist dashboard/dist

# /data holds flow_agent.db and output/. agent/ stays writable because
# PATCH /api/models, /api/providers and the active project write JSON there.
RUN mkdir -p /data && chown -R flowkit:flowkit /data /app/agent
USER flowkit

ENV FLOW_AGENT_DIR=/data \
    API_HOST=0.0.0.0 \
    API_PORT=8100 \
    WS_HOST=127.0.0.1 \
    WS_PORT=9222

VOLUME /data
EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=4)"

CMD ["python", "-m", "agent.main"]
