# One image recipe for every service. Pick the service with --build-arg SERVICE=<dir under services/>.
FROM python:3.13-slim
ARG SERVICE=web
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/libs
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY libs ./libs
COPY services/${SERVICE} ./service
WORKDIR /app/service
EXPOSE 5000
# One worker: each service runs a background event-subscriber thread.
CMD ["gunicorn", "-b", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "app:app"]
