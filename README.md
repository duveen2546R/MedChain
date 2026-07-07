# MedChain AI

**Privacy-preserving federated learning for medical AI, with an on-chain trust layer.**

MedChain lets hospitals, clinics, and research groups train a shared diagnostic model **without ever
sharing patient data**. Each hospital trains locally on its own records and submits only the resulting
model weights. A FastAPI coordinator stress-tests every update against a labeled validation set,
screens for data poisoning, aggregates the honest updates into a global model, and records every
contribution and reputation change on a blockchain — so the whole process is auditable and tamper-evident.

---

## Table of contents

- [Why MedChain](#why-medchain)
- [Key features](#key-features)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup (step by step)](#setup-step-by-step)
- [Roles & permissions](#roles--permissions)
- [Onboarding (invite-only)](#onboarding-invite-only)
- [Bring your own data (CSV)](#bring-your-own-data-csv)
- [Running the demo](#running-the-demo)
- [API reference](#api-reference)
- [Configuration reference](#configuration-reference)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Security notes](#security-notes)
- [Troubleshooting](#troubleshooting)

---

## Why MedChain

Medical AI is bottlenecked by data: the best models need large, diverse datasets, but patient records
are private, regulated, and siloed inside individual institutions. Centralizing that data is often
illegal, always risky, and rarely possible.

**Federated learning** flips the model: instead of moving data to the model, MedChain moves the model
to the data. Hospitals train locally and share only anonymous weight vectors. MedChain adds the pieces
that make this trustworthy in a real consortium:

| Problem | MedChain's answer |
| --- | --- |
| Raw patient data must never leave the hospital | Only weights + metrics are submitted; the API rejects payloads containing raw-data keys |
| A malicious or broken node could poison the model | Every update is gated on a labeled validation "digital twin" + a cross-hospital anomaly screen |
| Who contributed what, and can we trust them? | Every contribution + reputation change is recorded on-chain and independently verifiable |
| Reported accuracy can be faked | The server re-evaluates each update itself and flags implausible self-reported metrics |
| Onboarding must be controlled | Invite-only access with an access-request → admin-approval → invitation flow |

**Benefits:** train on data you could never centralize, keep full regulatory/privacy compliance, get a
tamper-evident audit trail for regulators, reward reliable contributors automatically, and give clinics
a confidence-scored diagnostic tool — all from one platform.

---

## Key features

**Federated training**
- Real logistic-regression training on each hospital's local data, warm-started from the global model.
- Sample-weighted federated averaging (FedAvg) of **verified updates only**.
- Objective-based routing: active, on-chain-registered hospitals are selected and weighted by reputation.

**Bring-your-own tabular data**
- A coordinator creates an objective by uploading a **labeled validation CSV**; the server derives the
  feature schema + standardization scaler + per-objective validation set from it.
- Each hospital fetches that schema (`GET /training-objectives/{id}/schema`) and trains on its **own CSV**.
- Legacy objectives with no schema fall back to a built-in breast-cancer model, so the demo runs
  out of the box.

**Integrity & anti-poisoning**
- **Digital-twin validation gate:** accuracy floor, regression check vs the current global model,
  update-magnitude cap, and reported-vs-evaluated metric plausibility.
- **Cross-hospital anomaly screen:** median/MAD outlier detection and opposing-direction rejection.
- Independent server-side evaluation of every aggregated model version.

**On-chain trust layer** (`MEDCHAIN_CHAIN_BACKEND`)
- `evm` (default): the real Solidity contracts (`ConsortiumRegistry`, `ReputationRegistry`,
  `TrainingLedger`) run on an **in-process EVM** deployed automatically at startup — no external node,
  no gas, no RPC provider. Reputation is owned by the contract. State is rebuilt from MongoDB on boot.
- `embedded`: a hand-rolled, ECDSA-signed, hash-linked ledger persisted in MongoDB and re-verified on
  every startup.
- Either way: hospital registration, contribution hashes, and reputation are on-chain; **model weights
  are never on-chain** (they live in Azure Blob Storage). `evm` automatically falls back to `embedded`
  if the EVM can't start.

**Auth & access control**
- Invite-only, multi-tenant, role-based. Access requests → admin approval → email invitation (Brevo) →
  token-based registration. Access + refresh token pairs, password reset, per-organization scoping.

**Diagnosis & audit**
- Confidence-scored inference from the real aggregated weights, with a specialist-consultation flag.
- Full audit trail + JSON compliance export; a signed block explorer for auditor roles.

---

## How it works

### The round lifecycle

```
  Coordinator                Hospital nodes                 MedChain backend            Blockchain
      |                            |                              |                          |
      | create objective          |                              |                          |
      | (upload validation CSV) -----------------------------> derive schema+scaler+twin      |
      |                            |                              |                          |
      | start round  ----------------------------------------> select active hospitals        |
      |                            |  fetch schema  <-------------|                          |
      |                            |  train on LOCAL data         |                          |
      |                            |  submit weights + metrics -> validate on digital twin    |
      |                            |                              |  (gate + anomaly screen) |
      |                            |                              |  FedAvg verified updates |
      |                            |                              |  record contributions ------> tx
      |                            |                              |  update reputation --------> tx
      |                            |                              |  publish new model version|
      | inspect model / audit  <---------------------------------|  verify chain            |
```

1. **Create an objective.** A coordinator uploads a small labeled validation CSV. The server derives the
   ordered feature columns, the scaler (per-feature mean/std), and a validation set.
2. **Start a round.** The backend selects active, on-chain-registered hospitals (weighted by reputation).
3. **Local training.** Each selected hospital fetches the objective schema, loads its own CSV,
   standardizes with the published scaler, trains warm-started from the current global weights, and
   submits **only** the weight vector + measured metrics.
4. **Gate.** Each submission is evaluated on the digital twin (accuracy floor, regression, magnitude cap,
   metric plausibility). Failures are rejected and never enter the model.
5. **Aggregate.** Once all selected hospitals respond, a cross-hospital anomaly screen removes outliers,
   surviving updates are FedAvg-averaged, and the aggregate is re-evaluated on the twin.
6. **Record.** Contributions and reputation changes are written on-chain; a new model version is published.
7. **Diagnose / audit.** Clinics run confidence-scored predictions; auditors verify the chain and export
   the audit trail.

Privacy holds throughout: only the *coordinator's own* labeled validation set reaches the server, and
each hospital's training data never leaves its machine — only weights + metrics.

---

## Architecture

```text
frontend/   React + Vite console (dashboard, diagnosis, chain explorer, audit, team/onboarding)
backend/    FastAPI service
              app/api/         routes, auth routes, dependencies (RBAC)
              app/services/    runtime orchestrator, validation gate, anomaly screen, FedAvg,
                               evaluation (digital twin), dataset schema derivation,
                               blockchain (embedded) + evm_blockchain (in-process EVM),
                               notifications (Brevo), audit, routing, artifacts (Azure Blob)
              app/store.py     async MongoDB repository
              tests/           pytest suite (in-memory repo, artifact store, EVM tester)
clients/    Federated hospital clients: node_agent.py (deployable), hospital_client.py,
            common.py (CSV loading + trainer), run_demo.py, generate_digital_twin.py, Dockerfile
contracts/  Solidity contracts + Hardhat (compiled artifacts are deployed by the EVM backend)
```

**Data stores:** MongoDB (operational state), Azure Blob Storage (model artifacts), the EVM/embedded
ledger (registrations, contribution hashes, reputation).

---

## Tech stack

- **Backend:** Python 3.11+ (tested on 3.13), FastAPI, Pydantic v2, Motor (async MongoDB), NumPy.
- **On-chain:** Solidity 0.8.28 + Hardhat; `web3.py` + `eth-tester`/`py-evm` (in-process EVM); `eth-account`.
- **Storage:** MongoDB Atlas, Azure Blob Storage.
- **Email:** Brevo transactional API (optional).
- **Frontend:** React 19 + Vite, React Router, Framer Motion.
- **Clients:** NumPy + scikit-learn (dataset/trainer) + Requests.

---

## Prerequisites

- **Python 3.11+** and **Node.js 18+** (Node is used for the frontend and to compile the contracts).
- A **MongoDB Atlas** cluster (or any MongoDB reachable over `mongodb+srv://` / `mongodb://`).
- An **Azure Blob Storage** account + private container.
- Optional: a **Brevo** account/API key for real invitation & password-reset emails.

---

## Setup (step by step)

### 1. Clone and enter the repo

```bash
git clone <your-fork-url> MedChain
cd MedChain
```

### 2. MongoDB Atlas

1. Create an Atlas cluster.
2. **Database Access →** create a database user (percent-encode special characters in the password).
3. **Network Access →** allow your current IP and each deployment server's egress IP.
4. **Connect → Drivers → Python →** copy the `mongodb+srv://...` string and replace the password placeholder.

You'll put this in `backend/.env` as `MEDCHAIN_MONGODB_URI` (step 5). Never place the Atlas URI in
`frontend/.env` — Vite values are visible in the browser.

### 3. Azure Blob Storage

1. Create a private Blob container, e.g. `medchain-artifacts`.
2. Local dev: either run `az login`, or copy a connection string from the account's **Access keys**.
3. Hosted on Azure: enable Managed Identity and grant it **Storage Blob Data Contributor** on the account.

`AZURE_STORAGE_CONNECTION_STRING` (if set) takes precedence over Managed Identity. The backend verifies
container access at startup and does not fall back to local disk.

### 4. Compile the smart contracts (for the EVM chain backend)

The default chain backend runs the real Solidity contracts on an in-process EVM. It reads the
**compiled artifacts** from `contracts/artifacts/`. These are committed, so this step is only needed if
you change the contracts or the artifacts are missing:

```bash
cd contracts
npm install
npx hardhat compile        # writes contracts/artifacts/**
npx hardhat test           # (optional) run the contract test suite
cd ..
```

To skip on-chain entirely, set `MEDCHAIN_CHAIN_BACKEND=embedded` (no contracts or artifacts needed).

### 5. Configure the backend environment

Copy the example and fill it in:

```bash
cp backend/.env.example backend/.env
openssl rand -hex 32        # use the output for MEDCHAIN_SECRET_KEY
```

Minimum required values in `backend/.env`:

```bash
MEDCHAIN_SECRET_KEY=<32+ random characters>
MEDCHAIN_MONGODB_URI=mongodb+srv://<user>:<password>@<cluster-host>/?retryWrites=true&w=majority
AZURE_STORAGE_CONTAINER=medchain-artifacts
AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net   # or AZURE_STORAGE_CONNECTION_STRING

# Create the first platform administrator (bootstrapped once on startup):
MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL=admin@yourorg.example
MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD=<at least 12 characters>
```

See the [Configuration reference](#configuration-reference) for every variable (email, token TTLs,
gate thresholds, chain backend, etc.).

### 6. Install & run the backend

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

On startup the backend validates settings, connects to MongoDB + Azure, deploys the contracts to the
in-process EVM (or loads the embedded ledger), and bootstraps the admin account. Health check:

```bash
curl http://localhost:8000/health
```

### 7. Install & run the frontend

```bash
cp frontend/.env.example frontend/.env    # VITE_MEDCHAIN_API_URL=http://localhost:8000
cd frontend
npm install
npm run dev                                # http://localhost:5173
```

### 8. Sign in

Open the frontend and sign in with the bootstrap admin credentials from step 5. Remove the bootstrap
password from the environment after the account exists.

---

## Roles & permissions

| Role | Can do |
| --- | --- |
| `platform_admin` | Everything: approve/reject access requests, invite **any** role into any org, create objectives, register hospitals on-chain, start rounds, run inference, view audit + chain |
| `hospital_admin` | Manage its own organization: invite `hospital_node` / `clinic_user` in its own org, create objectives, start rounds |
| `hospital_node` | Submit model updates for its own organization's hospital |
| `clinic_user` | Run confidence-scored diagnosis (`/inference/predict`) |
| `auditor` | Read the audit log, chain explorer, and produce compliance exports |
| `research_partner` | Read approved models and audit/chain metadata |

The first `platform_admin` is created **only** via the `MEDCHAIN_BOOTSTRAP_ADMIN_*` env vars. Everyone
else joins by invitation.

---

## Onboarding (invite-only)

There is no open signup. Access is granted like this:

1. **Request access** — a hospital/research org submits `POST /auth/access-requests` (public form at
   `/request-access`).
2. **Admin review** — a `platform_admin` approves it in the **Team** page, which creates the
   organization and an invitation.
3. **Invitation email** — the invitee receives a link (via Brevo). If email isn't configured, the invite
   link/token is returned to the admin in the API response and shown with a copy button.
4. **Register** — the invitee opens `/register?token=...` and sets a password (`POST /auth/register`),
   which activates the account and returns an access + refresh token pair.

Ongoing invites: `platform_admin` can invite anyone into any org; `hospital_admin` can invite
`hospital_node` / `clinic_user` into its **own** org only. **Clinics** (consumers of the model) are
created directly by an admin inviting a `clinic_user`. Password reset is available via
`POST /auth/forgot-password` → `POST /auth/reset-password` (anti-enumeration, single-use tokens).

Set `MEDCHAIN_BREVO_API_KEY` + `MEDCHAIN_MAIL_FROM_EMAIL` to send real emails; otherwise links are logged
server-side and surfaced in-app so the flow works offline.

---

## Bring your own data (CSV)

MedChain trains on **arbitrary tabular CSVs**, not just the built-in dataset.

**1. Create an objective with a validation set.** As an admin, use the **New training objective** panel
on the dashboard (or `POST /training-objectives`) and upload a small **labeled** CSV — feature columns
plus a target column (two classes). The server derives the schema, scaler, and validation set:

```jsonc
POST /training-objectives
{
  "name": "Diabetes risk model",
  "disease_category": "endocrinology",
  "specialty": "Endocrinology",
  "min_participants": 2,
  "validation_csv": "glucose,bmi,age,diagnosis\n148,33.6,50,positive\n85,26.6,31,negative\n...",
  "target_column": "diagnosis"          // optional; defaults to the last column
}
```

**2. Each hospital trains on its own CSV.** A node fetches the schema and standardizes with the
published scaler (so every participant preprocesses identically):

```bash
GET /training-objectives/{id}/schema
# → { feature_columns, target_column, scaler:{mean,scale}, n_features, expected_dimension,
#     positive_label, negative_label }
```

### Run a hospital node (real deployment)

A hospital runs the deployable agent on its own infrastructure, pointing at its own CSV. Raw data never
leaves the machine:

```bash
pip install -r clients/requirements.txt

MEDCHAIN_API=https://api.medchain.example \
MEDCHAIN_EMAIL=node@hospital.org MEDCHAIN_PASSWORD=... \
MEDCHAIN_HOSPITAL_ID=hsp_123 MEDCHAIN_OBJECTIVE_ID=obj_abc \
MEDCHAIN_CSV_PATH=/data/patients.csv \
python clients/node_agent.py watch          # or "participate" for a single round
```

Or with Docker (mount your CSV read-only; it stays on your host):

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

The local CSV must contain the objective's feature columns and target column.

---

## Running the demo

The end-to-end demo needs no external data — it generates per-hospital CSVs + a validation CSV from the
built-in breast-cancer dataset and drives the **real** pipeline (schema upload → local training →
gate → aggregate → on-chain records):

```bash
pip install -r clients/requirements.txt
python clients/run_demo.py \
  --admin-email admin@yourorg.example --admin-password <password> --rounds 3
```

Each round prints reported vs digital-twin-evaluated accuracy and the reputation table; the run ends
with a full chain verification. Demonstrate the poisoning gate live (hospital 2 submits negated weights,
gets rejected on the twin, loses reputation, and is excluded from the aggregate):

```bash
python clients/run_demo.py --admin-email ... --admin-password ... --poison 2
```

Regenerate the built-in fallback twin (requires scikit-learn):

```bash
python clients/generate_digital_twin.py     # writes backend/app/data/digital_twin.json
```

---

## API reference

Base URL defaults to `http://localhost:8000`. All non-public endpoints require
`Authorization: Bearer <access_token>`.

**Health**
- `GET /health` — service, Mongo, Azure, and blockchain status.

**Auth & onboarding**
- `POST /auth/access-requests` (public) · `GET /auth/access-requests` · `POST /auth/access-requests/{id}/approve|reject` (platform_admin)
- `POST /auth/invitations` · `GET /auth/invitations` · `POST /auth/invitations/{id}/revoke` · `GET /auth/invitations/token/{token}` (public preview)
- `POST /auth/register` (accept invitation) · `POST /auth/login` · `POST /auth/refresh` · `GET /me`
- `POST /auth/forgot-password` · `POST /auth/reset-password`

**Hospitals & objectives**
- `GET/POST/PATCH /hospitals` · `POST /hospitals/{id}/blockchain/register` · `GET /hospitals/{id}/reputation/history`
- `GET/POST /training-objectives` (optional `validation_csv` + `target_column`) · `GET /training-objectives/{id}/schema`

**Rounds, submissions & models**
- `GET/POST /rounds` · `GET /rounds/{id}` · `POST /rounds/{id}/cancel` · `POST /rounds/{id}/blockchain/retry`
- `POST /rounds/{id}/submissions` · `GET /rounds/{id}/validations`
- `GET /model-versions` · `GET /model-versions/current?objective_id=`
- `POST /inference/predict` — `{ "features": [...], "objective_id": "obj_..." }`

**Blockchain & audit**
- `GET /blockchain/blocks` · `GET /blockchain/verify` · `GET /blockchain/contributions`
- `GET /audit/events` · `GET /compliance/exports`

Submission body:

```json
{
  "hospital_id": "hsp_example",
  "update": {
    "weights": [0.12, -0.04, 0.81],
    "metrics": { "local_accuracy": 0.91, "loss": 0.18, "samples": 4200 },
    "schema_version": "medchain-update-v1"
  }
}
```

On a published model version, `accuracy` is the sample-weighted **client-reported** metric;
`evaluated_accuracy` is the independent **digital-twin** evaluation.

---

## Configuration reference

All backend config lives in `backend/.env` (see `backend/.env.example`). `*` = required.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MEDCHAIN_SECRET_KEY` * | — | ≥32 chars; signs tokens and (when unset) derives the chain authority key |
| `MEDCHAIN_MONGODB_URI` * | — | MongoDB connection string |
| `MEDCHAIN_MONGODB_NAME` | `medchain` | Database name |
| `AZURE_STORAGE_CONTAINER` * | — | Blob container for model artifacts |
| `AZURE_STORAGE_ACCOUNT_URL` / `AZURE_STORAGE_CONNECTION_STRING` * | — | One is required; connection string wins |
| `MEDCHAIN_CORS_ORIGINS` | localhost:5173 | Comma-separated allowed origins |
| `MEDCHAIN_ACCESS_TOKEN_MINUTES` | `120` | Access-token TTL |
| `MEDCHAIN_REFRESH_TOKEN_DAYS` | `14` | Refresh-token TTL |
| `MEDCHAIN_INVITATION_EXPIRES_DAYS` | `7` | Invitation validity |
| `MEDCHAIN_RESET_TOKEN_MINUTES` | `60` | Password-reset token validity |
| `MEDCHAIN_BREVO_API_KEY` | — | Brevo API key (email off when unset) |
| `MEDCHAIN_MAIL_FROM_EMAIL` | — | Required when Brevo key is set |
| `MEDCHAIN_MAIL_FROM_NAME` | `MedChain` | Sender name |
| `MEDCHAIN_FRONTEND_BASE_URL` | `http://localhost:5173` | Builds invite/reset links |
| `MEDCHAIN_CHAIN_BACKEND` | `evm` | `evm` (in-process contracts) or `embedded` (Mongo ledger) |
| `MEDCHAIN_CHAIN_ID` | `7777` | Reported chain id |
| `MEDCHAIN_SIGNER_PRIVATE_KEY` | derived | Embedded-ledger authority key (keep stable) |
| `MEDCHAIN_DIGITAL_TWIN_PATH` | `backend/app/data/digital_twin.json` | Built-in fallback twin |
| `MEDCHAIN_TWIN_FLOOR_ACCURACY` | `0.60` | Reject updates below this twin accuracy |
| `MEDCHAIN_TWIN_REGRESSION_TOLERANCE` | `0.05` | Max allowed regression vs global model |
| `MEDCHAIN_ANOMALY_DISTANCE_CAP` | `10.0` | Max weight distance from the global model |
| `MEDCHAIN_ANOMALY_MAD_THRESHOLD` | `3.5` | Cross-hospital outlier threshold |
| `MEDCHAIN_REPORTED_METRIC_TOLERANCE` | `0.30` | Max reported-vs-evaluated accuracy gap |
| `MEDCHAIN_REPUTATION_REWARD` / `_PENALTY` | `2` / `10` | Reputation deltas (embedded backend only) |
| `MEDCHAIN_INFERENCE_LOW_CONFIDENCE` | `0.70` | Below this → specialist-consultation flag |
| `MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` / `_NAME` | — | First platform admin (password ≥12 chars) |

Frontend: `frontend/.env` → `VITE_MEDCHAIN_API_URL` (browser-visible; never put secrets here).

---

## Testing

```bash
# Backend (in-memory Mongo + artifact store + EVM tester; no external services needed)
venv/bin/python -m pytest backend/tests -q

# Smart contracts
cd contracts && npx hardhat test

# Frontend production build (type/lint sanity)
cd frontend && npm run build
```

The backend suite covers auth/onboarding, the validation gate + anomaly screen, per-objective CSV
schemas, federated aggregation, confidence inference, and the real in-process EVM (deploy → register →
contribute → reputation → verify), including a full round driven end-to-end on the EVM backend.

---

## Project structure

```text
frontend/   React + Vite console
backend/    FastAPI service, async MongoDB repository, services, and pytest suite
clients/    Federated hospital clients, deployable node agent, demo orchestrator, twin generator
contracts/  Solidity contracts + Hardhat; compiled artifacts deployed by the EVM chain backend
```

Local `.env` files are git-ignored; committed `.env.example` files document required configuration.

---

## Security notes

- **No raw data leaves a hospital.** Only weights + metrics are submitted, and the API rejects payloads
  containing raw patient-data keys.
- **Only derived values are audit-logged** for inference — never the input feature vector.
- **The coordinator's validation set** is the only labeled data the server holds; it comes from whoever
  creates the objective, not from other hospitals.
- **Tokens** are short-lived access + longer-lived refresh pairs; refresh tokens can't be used as access
  tokens and vice-versa. Password reset is single-use and anti-enumerating.
- **On-chain data** is metadata + hashes only; model weights stay in private Blob Storage.
- Keep `MEDCHAIN_SECRET_KEY` (and `MEDCHAIN_SIGNER_PRIVATE_KEY` if set) stable and secret — the embedded
  chain rejects an authority-key change, and tokens/pepper depend on the secret.

---

## Troubleshooting

- **Backend won't start — settings error:** ensure `MEDCHAIN_SECRET_KEY` (≥32 chars),
  `MEDCHAIN_MONGODB_URI`, and the Azure container variables are set.
- **Mongo TLS/handshake errors:** your IP isn't allow-listed in Atlas Network Access (or you're behind a
  VPN/firewall). Add the egress IP.
- **EVM backend didn't come up:** it logs a warning and falls back to the embedded ledger. Ensure
  `contracts/artifacts/**` exist (`npx hardhat compile`) and `web3[tester]` is installed
  (`pip install -r backend/requirements.txt`). Force the ledger with `MEDCHAIN_CHAIN_BACKEND=embedded`.
- **No invitation email arrived:** Brevo isn't configured — the invite link is in the approve/create API
  response and shown in the Team page. Set `MEDCHAIN_BREVO_API_KEY` + `MEDCHAIN_MAIL_FROM_EMAIL` for real email.
- **Round won't start / "already active":** only one round runs at a time; cancel a stuck one with
  `POST /rounds/{id}/cancel`.
- **Submission rejected by the gate:** the update failed the digital-twin checks (accuracy floor,
  regression, magnitude, or implausible reported metrics) — inspect `GET /rounds/{id}/validations`.
