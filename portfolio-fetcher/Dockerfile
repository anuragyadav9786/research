# Docker runtime (not Render's plain Python buildpack) because tier2
# scrapers need a real Chromium install via Playwright, which the
# standard Python runtime has no path to install system dependencies
# for.
FROM python:3.11-slim

# System libraries Chromium needs to actually launch headless on a
# minimal Debian base (python:3.11-slim) — without these, Playwright's
# own browser binary install succeeds but the browser fails to start.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

ENTRYPOINT ["python", "main.py"]
