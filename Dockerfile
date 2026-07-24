FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
COPY vendor/wheels/ vendor/wheels/
RUN pip install --no-cache-dir --no-index --find-links=vendor/wheels -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-"]
