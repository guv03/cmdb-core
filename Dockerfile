FROM python:3.13-slim

WORKDIR /app

# 구성도(서비스 토폴로지) 화면이 dot 바이너리로 서버에서 SVG를 그린다(dashboard/topology.py) -
# 폐쇄망 배포라도 docker build 자체는 개발망에서 돌기 때문에(운영 K8s는 완성된 이미지만
# 받음) apt 설치가 그대로 통한다.
RUN apt-get update && apt-get install -y --no-install-recommends graphviz \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY vendor/wheels/ vendor/wheels/
RUN pip install --no-cache-dir --no-index --find-links=vendor/wheels -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--access-logfile", "-", "--error-logfile", "-"]
