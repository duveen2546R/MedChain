# MedChain hospital clients

Real federated-learning participants. Each hospital trains a logistic-regression
diagnostic model on its **own local data** and submits only the weight vector plus
measured metrics — raw rows never leave the client. Two data sources are supported:

- **Bring-your-own CSV (real mode):** the coordinator creates a training objective by
  uploading a labeled validation CSV; the server derives the feature schema + scaler.
  Each node fetches that schema and trains on its own CSV with matching columns.
- **Built-in dataset (demo mode):** a shard of scikit-learn's breast-cancer dataset,
  used by `run_demo.py` so the whole flow runs out of the box.

## Independent node agent (real deployment)

A hospital runs the agent on its own infrastructure, pointing at its own CSV. It never
uploads raw data. Configure via env vars (see `node_agent.py`) and run `participate`
(one round) or `watch` (auto-join open rounds):

```bash
MEDCHAIN_API=https://api.medchain.example \
MEDCHAIN_EMAIL=node@hospital.org MEDCHAIN_PASSWORD=... \
MEDCHAIN_HOSPITAL_ID=hsp_123 MEDCHAIN_OBJECTIVE_ID=obj_abc \
MEDCHAIN_CSV_PATH=/data/patients.csv \
python clients/node_agent.py watch
```

Or with Docker (mount your CSV read-only; data stays on your host):

```bash
docker build -t medchain-node clients/
docker run --rm \
  -e MEDCHAIN_API=https://api.medchain.example \
  -e MEDCHAIN_EMAIL=node@hospital.org -e MEDCHAIN_PASSWORD=... \
  -e MEDCHAIN_HOSPITAL_ID=hsp_123 -e MEDCHAIN_OBJECTIVE_ID=obj_abc \
  -e MEDCHAIN_CSV_PATH=/data/patients.csv \
  -v /local/patients.csv:/data/patients.csv:ro \
  medchain-node watch
```

The local CSV must contain the objective's feature columns and target column (fetch
them from `GET /training-objectives/{id}/schema`).

## Setup

```bash
pip install -r clients/requirements.txt
```

The backend needs a platform administrator. Set `MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL`
and `MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD` in `backend/.env` before first start.

## Full demo (3 hospitals, 3 rounds)

```bash
python clients/run_demo.py \
  --admin-email admin@example.com --admin-password <password> --rounds 3
```

Idempotent: hospital accounts, records, and on-chain registrations are reused on
re-runs. Each round prints reported vs digital-twin-evaluated accuracy and the
reputation table, and the run ends with a full chain verification.

Demo the poisoning gate (hospital 2 submits negated weights, gets rejected on
the digital twin, loses reputation, and is excluded from the aggregate):

```bash
python clients/run_demo.py --admin-email ... --admin-password ... --poison 2
```

## Single hospital, single round

```bash
python clients/hospital_client.py \
  --email hospital1@demo.medchain --password demo-hospital-pass-1 \
  --hospital-id hsp_demo_1 --round-id <round_id> --index 0 --total 3
```

## Regenerate the server-side digital twin

```bash
python clients/generate_digital_twin.py   # writes backend/app/data/digital_twin.json
```
