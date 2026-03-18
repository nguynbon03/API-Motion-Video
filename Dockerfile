FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY kling_tool/ ./kling_tool/
COPY kling_proxy/ ./kling_proxy/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Install Playwright Chromium browser
RUN playwright install chromium

# Create data directories
RUN mkdir -p /data/sessions /data/inputs/images /data/inputs/videos \
    /data/outputs /data/accounts /data/screenshots /data/logs

# Environment
ENV KLING_DATA_DIR=/data
ENV KLING_HEADLESS=true
ENV KLING_HOST=0.0.0.0
ENV KLING_PORT=8686

EXPOSE 8686

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8686/health').raise_for_status()"

CMD ["python", "-m", "uvicorn", "kling_tool.server:app", "--host", "0.0.0.0", "--port", "8686"]
