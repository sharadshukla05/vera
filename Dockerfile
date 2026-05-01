FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the entire project into the container
COPY . /app/

# Create a non-root user (Hugging Face Spaces requirement)
RUN useradd -m -u 1000 user
USER user

# Set environment variables
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PORT=7860

# Command to run the bot server
CMD ["python", "bot_server.py"]
