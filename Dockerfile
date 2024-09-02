# Use an official Python 3.12 image as a base
FROM python:3.12-slim

# Set the working directory to /
WORKDIR /

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Copy the application code
COPY . .

# Expose the port used by Django
EXPOSE 8000

# Run the command to start the Django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]