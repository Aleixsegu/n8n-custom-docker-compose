FROM python:3.11-slim

# Install system dependencies
# build-essential and cmake are required to build llama-cpp-python
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for CMAKE (optimize for generic CPU)
# Using generic settings to ensure compatibility
ENV CMAKE_ARGS="-DLLAMA_BLAS=OFF"

WORKDIR /app

COPY requirements.txt .

# Install dependencies
# We use --no-cache-dir to keep image small
# We force reinstall of llama-cpp-python to ensure it compiles with our CMAKE_ARGS
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Create cache directory for models
RUN mkdir -p /root/.cache/huggingface

EXPOSE 8083

CMD ["python", "app.py"]
