# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm

# Avoid interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- System dependencies + Node 20 -----------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        gnupg \
        sudo \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Python dependencies -----------------------------------------------------
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- Node dependencies + Playwright/Chromium --------------------------------
COPY package.json ./
COPY package-lock.json* ./
RUN npm install \
    && npx playwright install --with-deps chromium \
    && sudo npx playwright install-deps chromium || true

# --- Application code --------------------------------------------------------
COPY . .

CMD ["python", "bot.py"]
