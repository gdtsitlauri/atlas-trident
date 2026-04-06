FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY config /app/config
COPY src /app/src
COPY dashboard /app/dashboard
COPY experiments /app/experiments
COPY scripts /app/scripts

RUN mkdir -p /app/logs/latest

EXPOSE 8000
EXPOSE 8501

CMD ["python", "-m", "atlas.main", "--steps", "5"]
