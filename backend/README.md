# MedChain Backend

FastAPI service for coordinating externally trained federated model updates.

## Requirements

- Python 3.11+
- MongoDB Atlas
- A private Azure Blob Storage container
- An EVM JSON-RPC endpoint and a funded deployment wallet
- A unique `MEDCHAIN_SECRET_KEY` with at least 32 characters

The service fails startup when required configuration is missing, MongoDB cannot be reached, or
the Azure Blob container is inaccessible. There is no in-memory or local-file production fallback.

## Run

From the repository root:

Configure `MEDCHAIN_MONGODB_URI` with the connection string from Atlas **Connect → Drivers → Python**.
The Atlas database user needs read/write access to the configured `MEDCHAIN_MONGODB_NAME`, and
the machine running FastAPI must be allowed under Atlas **Network Access**.

For Azure Blob Storage, create a private container and configure one authentication method:

```env
# Recommended for an Azure-hosted backend using Managed Identity
AZURE_STORAGE_ACCOUNT_URL=https://<storage-account>.blob.core.windows.net
AZURE_STORAGE_CONTAINER=medchain-artifacts

# Or use this for local development; it takes precedence when set
AZURE_STORAGE_CONNECTION_STRING=
```

Managed Identity requires the **Storage Blob Data Contributor** role. Locally,
`DefaultAzureCredential` can use an `az login` session when no connection string is supplied.

Deploy the contracts using the same dedicated wallet that the backend will use to sign ledger
transactions:

```bash
cd contracts
npm install
npm test
npm run deploy -- --network configured
```

Before deployment, set `MEDCHAIN_EVM_RPC_URL`, `MEDCHAIN_EVM_CHAIN_ID`, and
`MEDCHAIN_EVM_SIGNER_PRIVATE_KEY` in `backend/.env`. Copy the three deployed contract addresses
printed by the deployment script into the matching `MEDCHAIN_*_ADDRESS` values. Never use a wallet
that holds production treasury funds.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Configuration is loaded from `backend/.env`. To provision the initial platform administrator,
set these values before the first start:

```env
MEDCHAIN_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
MEDCHAIN_BOOTSTRAP_ADMIN_PASSWORD=replace-with-a-strong-password
MEDCHAIN_BOOTSTRAP_ADMIN_NAME=Platform Administrator
```

Remove the bootstrap password from the deployment environment after the account is created.

## API surface

- `GET /health`
- `POST /auth/login`, `POST /auth/refresh` (access + refresh token pair), `GET /me`
- Invite-only onboarding:
  - `POST /auth/access-requests` (public), `GET /auth/access-requests`, `POST /auth/access-requests/{id}/approve|reject` (platform_admin)
  - `POST /auth/invitations` (platform_admin: any role/org; hospital_admin: hospital_node/clinic_user in own org), `GET /auth/invitations`, `POST /auth/invitations/{id}/revoke`
  - `GET /auth/invitations/token/{token}` (public preview), `POST /auth/register` (accept invitation → token pair)
  - `POST /auth/forgot-password`, `POST /auth/reset-password`
- `GET /dashboard/summary`
- `GET/POST/PATCH /hospitals`
- `POST /hospitals/{id}/blockchain/register`
- `GET/POST /training-objectives`
- `GET/POST /rounds`, `GET /rounds/{id}`
- `POST /rounds/{id}/submissions`
- `POST /rounds/{id}/blockchain/retry`
- `GET /model-versions`, `GET /model-versions/current`
- `GET /blockchain/contributions`
- `GET /audit/events`, `GET /compliance/exports`

The update endpoint accepts model weights and numeric metrics. It rejects payload keys associated
with raw patient records. Actual hospital training and global model serving are deliberately outside
the backend rather than being simulated.

Every hospital needs a unique EVM `wallet_address`. A platform administrator must call the
blockchain registration endpoint before the hospital is eligible for routing. When a round closes,
the backend signs `TrainingLedger.recordContribution(...)` for every verified or rejected update,
waits for a successful receipt, and stores the transaction hash and block number in MongoDB Atlas.
