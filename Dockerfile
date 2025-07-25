# Dockerfile for bot_arbitratge
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy all project files into the container
COPY . /app

# Install dependencies if requirements.txt exists
RUN mkdir -p /app/logs && chmod 777 /app/logs
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Run your main.py script
CMD ["python", "-m", "src.main"]
