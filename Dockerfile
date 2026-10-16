FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py icon.png icon-512.png ./
ENV PORT=8000
# Tek işçi: işler bellekte tutulduğu için birden fazla işçi kullanılmamalı
CMD gunicorn -w 1 --threads 8 -t 0 -b 0.0.0.0:$PORT app:app
