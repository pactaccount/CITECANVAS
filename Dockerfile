FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EVID_LOCAL_STORAGE_DIR=/var/lib/evid/pages

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 evid && \
    mkdir -p /var/lib/evid/pages && \
    chown -R evid:evid /app /var/lib/evid
USER evid

EXPOSE 8000
CMD ["sh", "-c", "python scripts/migrate.py && exec python scripts/serve.py"]
