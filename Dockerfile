# Use a lightweight Python image
FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Copy all files into the container
COPY . .

# Ensure the cache directory exists and is writable
RUN mkdir -p /app/cache && chmod -R 777 /app/cache

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Set environment variables for Hugging Face model caching
ENV HF_HOME=/app/cache
ENV TRANSFORMERS_CACHE=/app/cache
ENV TORCH_HOME=/app/cache

# Expose port (for Spaces, default 7860 or 5000 is fine)
EXPOSE 5000

# Start your Flask app
CMD ["python", "app.py"]
