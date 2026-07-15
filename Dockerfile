FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
COPY vendor/wheels/ vendor/wheels/
RUN pip install --no-cache-dir --no-index --find-links=vendor/wheels -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
