# 1. Use an official, lightweight Python runtime as a parent image
FROM python:3.11-slim

# 2. Set system environment configurations
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Establish our internal working directory
WORKDIR /workspace

# 4. Install essential system dependencies required for building wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 6. Copy the entire application source code into the container
COPY . .

# 7. Expose the port FastAPI will listen on
EXPOSE 8000

# 8. Command to run the application using Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]