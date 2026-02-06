FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp and Flask
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    yt-dlp \
    flask \
    flask-cors

# Create downloads directory
RUN mkdir -p /downloads

# Copy application
COPY app.py /app/app.py

WORKDIR /app

# Expose service port
EXPOSE 8082

# Start application
CMD ["python", "app.py"]
