FROM node:22.23.5-bookworm-slim AS javascript-runtime
FROM python:3.12.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATABASE=/app/data/recruiting.sqlite3 HOST=0.0.0.0 PORT=8080
WORKDIR /app
COPY --from=javascript-runtime /usr/local/bin/node /usr/local/bin/node
COPY requirements.lock requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 student && mkdir /app/data && chown student:student /app /app/data
COPY --chown=student:student . .
USER student
EXPOSE 8080
CMD ["sh", "-c", "python -m flask --app recruiting init-db && exec python -m recruiting"]
