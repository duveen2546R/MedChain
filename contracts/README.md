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

## Deploy

Set the EVM values in `backend/.env`, then deploy with the backend's dedicated signer wallet:

```bash
npm install
npm test
npm run deploy -- --network configured
```

Copy the printed registry, reputation, and ledger addresses into `backend/.env`. The FastAPI runtime
validates the chain ID, deployed bytecode, contract ownership, and registry wiring at startup. It
then uses Web3.py to register hospital wallets and submit confirmed contribution transactions.
