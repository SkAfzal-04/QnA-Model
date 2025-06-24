# Use a lightweight official Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy only requirements first to leverage caching
COPY requirements.txt .

# Install system dependencies and Python packages
RUN apt-get update && \
    apt-get install -y build-essential && \
    pip install --no-cache-dir -r requirements.txt

# Copy rest of the application code
COPY . .

# Expose the port expected by Hugging Face Spaces
EXPOSE 7860

# Set environment variables (override in Hugging Face settings if needed)
ENV PORT=7860

# Start the Flask server
CMD ["python", "app.py"]
