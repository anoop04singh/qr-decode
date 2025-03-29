# Use an official lightweight Python image
FROM python:3.9-slim

# Install system dependencies, including libzbar0
RUN apt-get update && \
    apt-get install -y libzbar0 && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose port 5000 (Vercel will map the correct PORT environment variable)
EXPOSE 5000

# Use Gunicorn to serve the Flask application.
# Replace "app:app" with your module and application variable if different.
CMD ["gunicorn", "app:app"]
