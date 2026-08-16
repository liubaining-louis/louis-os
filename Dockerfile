FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY . /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && addgroup --system louis \
    && adduser --system --ingroup louis --home /home/louis louis \
    && chown -R louis:louis /app /ms-playwright /home/louis

USER louis

EXPOSE 8080

CMD ["python", "-m", "atlas.server"]
