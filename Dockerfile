FROM python:3.11-slim

LABEL maintainer="DownTube"
LABEL description="Local YouTube Downloader with Arabic Subtitles"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create download directory
RUN mkdir -p /root/Downloads/DownTube

# Expose port
EXPOSE 8555

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8555/api/status || exit 1

# Run the application
CMD ["python", "app.py", "--no-browser", "--port", "8555"]
