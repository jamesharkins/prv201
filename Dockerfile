# Differential demo image: ngspice + the pinned Python stack + committed models.
FROM python:3.11-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ngspice fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY differential ./differential
COPY eval ./eval
RUN pip install --no-cache-dir -e .

COPY circuits ./circuits
COPY data/models ./data/models
COPY data/eval ./data/eval
COPY results ./results

ENV HOST=0.0.0.0 PORT=8000 DIFFERENTIAL_MODE=offline
EXPOSE 8000
CMD ["python", "-m", "differential.app.server"]
