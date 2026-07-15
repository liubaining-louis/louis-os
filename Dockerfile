FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY . /app

RUN python -m pip install --no-cache-dir .

EXPOSE 8080

CMD ["python", "-m", "atlas.server"]
