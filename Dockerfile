# Use an official Python runtime as a parent image
FROM python:3.7-slim

# Set the working directory to /app
WORKDIR /app

# Copy requirements into the container at /app
COPY requirements.txt /app

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r requirements.txt

# Copy the files into the container at /app
COPY food_optimizer.py /app

# Run "food_optimizer.py" when the container launches
CMD ["python", "food_optimizer.py"]