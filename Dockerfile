FROM python:3.11-slim

# Install system dependencies required by Chromium (used by Playwright)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (includes playwright)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download Chromium binaries for Playwright
RUN playwright install chromium

# Copy application code
COPY . .

CMD ["python", "bot.py"]
