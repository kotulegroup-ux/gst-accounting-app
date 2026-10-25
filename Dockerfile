FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Initialize database
RUN python -c "from app.database import init_db; init_db()"

EXPOSE 7860

# Run uvicorn on PORT env variable or default 7860 (HuggingFace/Render compatible)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
