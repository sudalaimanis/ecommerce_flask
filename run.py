
m flask import Flask, request, Response
from prometheus_client import Counter, Histogram, generate_latest

app = Flask(__name__)

# Metrics
REQUEST_COUNT = Counter(
            'http_requests_total',
                'Total HTTP Requests',
                    ['method', 'endpoint', 'status']
                    )

REQUEST_LATENCY = Histogram(
            'http_request_duration_seconds',
                'Request latency',
                    ['endpoint']
                    )

@app.route('/')
def home():
        with REQUEST_LATENCY.labels(endpoint='/').time():
                    REQUEST_COUNT.labels(method='GET', endpoint='/', status='200').inc()
                            return "Hello World"

                        @app.route('/metrics')
                        def metrics():
                                return Response(generate_latest(), mimetype='text/plain')
