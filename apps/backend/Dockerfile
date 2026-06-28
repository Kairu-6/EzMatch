# Backend container for any Docker host (Render / Railway / Fly.io / Cloud Run).
# Python 3.12 is used (not 3.14) for the widest prebuilt-wheel availability for
# pandas / pymupdf / Pillow — the code uses no 3.13+ features.
FROM python:3.12-slim

# Tesseract OCR — the one dependency you CANNOT pip-install. With it on PATH,
# pytesseract finds it automatically (leave TESSERACT_CMD unset; that env var is
# only for pointing at tesseract.exe on Windows).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hosts inject the port to bind via $PORT; default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} expands at runtime.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
