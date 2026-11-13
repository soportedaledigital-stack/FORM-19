FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_THREAD_LIMIT=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py form19_core.py ./
COPY templates ./templates
COPY static ./static
# Essential: the original Dockerfile omitted this folder.
COPY data ./data
RUN python -c "from pathlib import Path; from form19_core import is_valid_book; is_valid_book(Path('data/FORM19_PLANTILLA.xlsm').read_bytes()); print('Plantilla FORM19 verificada')"
RUN useradd -m -u 10001 appuser
USER appuser
ENV PORT=10000
EXPOSE 10000
# One worker: the XLSM/file transactions use an in-process lock.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 90 --access-logfile - --error-logfile - app:app"]
