# MedChain AI Contracts

Private EVM contracts for the pilot MVP.

## Contracts

- `ConsortiumRegistry`: approved hospital nodes, org ids, roles, and active status.
- `TrainingLedger`: immutable contribution metadata, model version, artifact CID, validation status, and update hash.
- `ReputationRegistry`: contributor reputation changes driven by accepted/rejected ledger submissions.

## Run

```bash
cd contracts
npm install
npm test
```

These contracts are standalone and are not connected to the FastAPI runtime. The backend does not
claim on-chain persistence or fabricate transaction hashes. Integrating a deployed contract would
require a separate, explicit transaction adapter and deployment configuration.
