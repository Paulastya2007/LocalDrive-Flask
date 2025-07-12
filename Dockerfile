# Use the official Python slim image as the base
FROM python:3.13-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Copy the application code
COPY . .

# Expose the port the app will run on
EXPOSE 5000

# Declare volumes for persistent data
VOLUME /app/uploads
VOLUME /app/data

# Command to run the Flask app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
