FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY apps ./apps

EXPOSE 8001

CMD ["uvicorn", "apps.cpu_bound.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]