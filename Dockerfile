# Use an official lightweight Python image.
FROM python:3.9-slim

# Set the working directory in the container.
WORKDIR /app

# Copy the requirements file into the container.
COPY requirements.txt .

# Install system dependencies required for WMF conversion.
RUN apt-get update \
    && apt-get install -y --no-install-recommends inkscape \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . .

# Expose port 8080.
EXPOSE 8080

# Command to run the application using uvicorn.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
