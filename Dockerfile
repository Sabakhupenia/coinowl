# CoinOwl Dockerfile — Railway / Fly / any container host.
#
# Why this exists:
#   kaleido >= 1.0 (pinned in requirements.txt because 0.2.x is broken on
#   modern Python) renders Plotly figures via headless Chromium. It does
#   NOT bundle a binary. The default Railway Railpack image is python-only,
#   no browser — every chart tool fails at runtime with:
#       "Kaleido requires Google Chrome to be installed."
#
#   Installing chromium via apt at image-build time is the most reliable
#   path: stable system binary on PATH, kaleido's auto-detect finds it,
#   no fragile download-at-deploy-time logic.
#
# To use on Railway:
#   Service → Settings → Build → Build Provider → switch to "Dockerfile"
#   Railway auto-detects this file at repo root on next deploy.

FROM python:3.12-slim

# Chromium + the small set of system libs it actually needs to start
# headless. ca-certificates so kaleido's outbound HTTPS works; fonts-liberation
# so rendered text isn't blocky.
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        ca-certificates \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first so the pip-install layer caches when only source
# code changes between deploys.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source last — changes most often.
COPY . .

# Telethon writes its .session file relative to cwd; Railway provides a
# writable /app. For stateless deploys, TELEGRAM_SESSION_STRING env var is
# preferred over the .session file (see scripts/dump_session.py).
CMD ["python", "main.py"]
