# MedChain AI

MedChain is a backend-coordinated federated-learning service. Hospital clients (see `clients/`)
train a real logistic-regression diagnostic model on their local data shards and submit weight
vectors plus measured metrics through the authenticated API. The FastAPI service stress-tests each
update against a synthetic digital twin, screens for poisoning, performs sample-weighted federated
averaging, persists operational state in MongoDB, stores artifacts privately in Azure Blob Storage,
and records every contribution and reputation change on an embedded consortium blockchain.

## Implemented features

- Account registration, login, bearer authentication, and role-based authorization.
- MongoDB-backed organizations, hospitals, objectives, rounds, submissions, model versions, and audit events.
- Objective-based selection of active hospital participants, weighted by on-chain reputation.
- Organization-bound model update submission with raw patient-data key rejection.
- Digital-twin validation gate: every update is evaluated on a synthetic stress-test set before it
  can join the global model (accuracy floor, regression check, magnitude cap, reported-metric
  plausibility) plus a cross-client anomaly screen (median/MAD outliers, opposing directions).
- Sample-weighted federated averaging of verified updates only, with independent server-side
  (digital-twin) evaluation of every aggregated model version.
- Dynamic on-chain reputation: verified contributions earn reputation, rejected ones lose it, and
  hospital routing genuinely favors reliable nodes; full history at
  `GET /hospitals/{id}/reputation/history`.
- Real confidence-based inference (`POST /inference/predict`): predictions from the actual
  aggregated global weights, with confidence tiers and a specialist-consultation flag for
  low-confidence cases. Only derived values are audit-logged, never raw features.
- Mandatory Azure Blob Storage for model updates and aggregated model artifacts.
- Embedded consortium blockchain: signed, hash-linked blocks for hospital registration, contribution hashes, and reputation, verified on every startup.
- Authenticated dashboard: reported vs twin-evaluated accuracy, gate rejections, reputation deltas, and a block explorer for audit roles.
- Real federated hospital clients and an end-to-end demo: `python clients/run_demo.py` (see `clients/README.md`), including a `--poison` mode that demonstrates the gate live.

## MongoDB Atlas setup

1. Create an Atlas cluster.
2. Under **Database Access**, create a database user.
3. Under **Network Access**, allow your current IP address and each deployment server's egress IP.
4. Open **Connect → Drivers → Python**, copy the `mongodb+srv://...` connection string, and replace its password placeholder.
5. Put the connection string in `backend/.env` as `MEDCHAIN_MONGODB_URI`.

Percent-encode special characters in the username or password. Do not place the Atlas URI in
`frontend/.env`; Vite environment values are visible in the browser.

## Azure Blob Storage setup

1. Create a private Blob container, for example `medchain-artifacts`.
2. For a backend hosted on Azure, enable Managed Identity and grant it **Storage Blob Data Contributor** on the storage account or container.
3. Set `AZURE_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net` and `AZURE_STORAGE_CONTAINER=medchain-artifacts`.
4. For local development, either sign in with `az login` or set `AZURE_STORAGE_CONNECTION_STRING` from the storage account's **Access keys** page.

When `AZURE_STORAGE_CONNECTION_STRING` is present it takes precedence over Managed Identity.
The backend validates container access during startup and does not fall back to local disk.

## Blockchain setup

None required. The backend runs an embedded consortium blockchain: hash-linked, ECDSA-signed
blocks persisted in the `blockchain_blocks` MongoDB collection. It starts automatically with the
API — no local node, RPC provider, contract deployment, or address configuration.

The chain enforces the same rules the Solidity contracts did: hospital wallets register to exactly
one organization, reputation is seeded once, and each round accepts one contribution per wallet.
Every block header commits to the previous block hash and the merkle root of its transactions, and
the whole chain is re-verified on startup, so tampering with stored history fails the boot.
Only metadata and content hashes go on-chain; model weights stay in Azure Blob Storage.

Optional environment values:

- `MEDCHAIN_CHAIN_ID` (default `7777`).
- `MEDCHAIN_SIGNER_PRIVATE_KEY` — the consortium authority key that signs blocks. When unset, a
  key is derived from `MEDCHAIN_SECRET_KEY`. Keep whichever is used stable; the stored chain
  rejects an authority change.

Auditor-facing endpoints: `GET /blockchain/blocks` (signed block explorer),
`GET /blockchain/verify` (full integrity check), and `GET /blockchain/contributions`.

The Solidity contracts in `contracts/` are kept as the reference EVM implementation of the same
rules and are no longer required to run the application.

## Application setup

Configure the remaining values in `backend/.env`:

```bash
openssl rand -hex 32
```

Use that output for `MEDCHAIN_SECRET_KEY`. To create the first platform administrator, also set
`MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL` and `MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD`. The password must have
at least 12 characters. The account is created once and is not overwritten on later starts.

Start the backend from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend reads `frontend/.env` and expects the API at `VITE_MEDCHAIN_API_URL`.

## Real update workflow

1. A platform administrator creates hospital records with wallet addresses and registers those wallets on-chain.
2. An authorized administrator creates a round with `POST /rounds`.
3. The backend selects active hospitals and waits for their clients.
4. Each selected hospital submits its actual update to `POST /rounds/{round_id}/submissions`.
5. After every selected hospital responds, the backend aggregates verified updates, records every contribution on-chain, and creates a model version.

Submission body:

```json
{
  "hospital_id": "hsp_example",
  "update": {
    "weights": [0.12, -0.04, 0.81],
    "metrics": {
      "local_accuracy": 0.91,
      "loss": 0.18,
      "samples": 4200
    },
    "schema_version": "medchain-update-v1"
  }
}
```

`accuracy` on a generated model version is explicitly a sample-weighted client-reported metric;
it is not presented as an independently evaluated global accuracy.

## Project structure

```text
frontend/        React/Vite API client
backend/         FastAPI service, MongoDB repository, services, and tests
clients/         Real federated hospital clients, demo orchestrator, digital-twin generator
contracts/       Reference Solidity contracts (not required to run the application)
```

Local `.env` files are ignored. Committed `.env.example` files document required configuration.
