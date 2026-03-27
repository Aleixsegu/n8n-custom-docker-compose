FROM python:3.11-slim

# Install system dependencies
# ffmpeg is the main tool here. We install the full version to support most codecs.
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    flask \
    flask-cors

# Create directory for custom fonts
RUN mkdir -p /app/fonts

# Copy custom fonts if any (User should place .ttf files here)
COPY fonts/*.ttf /usr/share/fonts/truetype/custom/

# Update font cache
RUN fc-cache -f -v

# Create downloads directory (shared volume)
RUN mkdir -p /downloads

# Copy application
COPY app.py /app/app.py

WORKDIR /app

# Expose service port
EXPOSE 8084

# Start application
CMD ["python", "app.py"]
