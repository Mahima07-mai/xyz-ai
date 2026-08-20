FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2-binary / bcrypt wheels on slim images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Install production deps only -- requirements-dev.txt (pytest) is
# intentionally NOT copied/installed into the image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# OPENROUTER_API_KEY, JWT_SECRET, DATABASE_URL are required at runtime
# (see app/config.py) -- pass them via `docker run -e` / your
# orchestrator's secrets mechanism, never bake them into the image.
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
