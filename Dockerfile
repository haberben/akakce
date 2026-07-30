# Use official Playwright Python image which contains chromium and all system dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set environmental variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set workspace folder
WORKDIR /app

# Copy dependency list
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . /app/

# Expose server port
EXPOSE 8000

# Run the app
CMD ["python", "run.py"]
