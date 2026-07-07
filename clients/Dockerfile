# MedChain hospital node agent — run a federated participant on your own infrastructure.
# Your data stays in the mounted CSV; only weights + metrics are submitted.
FROM python:3.12-slim

WORKDIR /node
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common.py hospital_client.py node_agent.py ./

# Config is supplied at runtime via env vars (see node_agent.py). Mount your CSV read-only.
ENTRYPOINT ["python", "node_agent.py"]
CMD ["watch"]
