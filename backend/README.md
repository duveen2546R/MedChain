# MedChain Backend

FastAPI service for coordinating externally trained federated model updates.

## Requirements

- Python 3.11+
- MongoDB Atlas
- A private Azure Blob Storage container
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
- `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `GET /me`
- `GET /dashboard/summary`
- `GET/POST/PATCH /hospitals`
- `GET/POST /training-objectives`
- `GET/POST /rounds`, `GET /rounds/{id}`
- `POST /rounds/{id}/submissions`
- `GET /model-versions`, `GET /model-versions/current`
- `GET /audit/events`, `GET /compliance/exports`

The update endpoint accepts model weights and numeric metrics. It rejects payload keys associated
with raw patient records. Actual hospital training and global model serving are deliberately outside
the backend rather than being simulated.
