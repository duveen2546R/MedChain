# MedChain AI

MedChain is a backend-coordinated federated model-update service. Hospital clients train models
outside this repository and submit weight vectors plus measured metrics through the authenticated
API. The FastAPI service validates submissions, persists operational state in MongoDB, stores
artifacts privately in Azure Blob Storage, and performs sample-weighted federated averaging.

The application has no browser-side training simulation, synthetic server-side trainer, random
inference endpoint, in-memory production repository, demo accounts, or fabricated blockchain
transactions.

## Implemented features

- Account registration, login, bearer authentication, and role-based authorization.
- MongoDB-backed organizations, hospitals, objectives, rounds, submissions, model versions, and audit events.
- Objective-based selection of active hospital participants.
- Organization-bound model update submission with raw patient-data key rejection.
- Model schema, dimension, metric, and sample-count validation.
- Sample-weighted federated averaging based only on hospital-submitted updates.
- Mandatory Azure Blob Storage for model updates and aggregated model artifacts.
- Confirmed EVM transactions for hospital registration, contribution hashes, and reputation updates.
- Authenticated dashboard polling real backend state.

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

Use an EVM RPC provider and a dedicated funded wallet. Add the RPC URL, chain ID, and private key
to `backend/.env`, deploy the contracts, then copy the printed addresses back into the environment:

```bash
cd contracts
npm install
npm test
npm run deploy -- --network configured
```

The deployment wallet remains owner of all three contracts because the backend uses it to register
hospital wallets and sign `TrainingLedger.recordContribution` transactions. For production, place
the private key in the hosting platform's secret manager rather than a checked-in file.

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
contracts/       Solidity contracts, tests, and deployment script used by FastAPI
```

Local `.env` files are ignored. Committed `.env.example` files document required configuration.
