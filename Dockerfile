# Use official Python image
FROM python:3.11-slim

# Install ffmpeg and system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    build-essential \
    git \
    libsndfile1 \
 && rm -rf /var/lib/apt/lists/*

# Create app dir
WORKDIR /app

# Copy requirements and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy code
COPY . /app

# Set environment
ENV PYTHONUNBUFFERED=1

# Expose port (not required for polling bot)
EXPOSE 8080

# Run
CMD ["python", "main.py"]
