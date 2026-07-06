# MedChain hospital clients

Real federated-learning participants. Each hospital trains a logistic-regression
diagnostic model (breast-cancer dataset, 30 features) on its own deterministic
data shard and submits only the 31-dim weight vector plus measured metrics.
Raw rows never leave the client.

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
