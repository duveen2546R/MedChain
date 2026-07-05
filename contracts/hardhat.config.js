import "@nomicfoundation/hardhat-toolbox";
import dotenv from "dotenv";

dotenv.config({ path: "../backend/.env" });

const configuredNetwork = process.env.MEDCHAIN_EVM_RPC_URL && process.env.MEDCHAIN_EVM_SIGNER_PRIVATE_KEY
  ? {
      configured: {
        url: process.env.MEDCHAIN_EVM_RPC_URL,
        chainId: Number(process.env.MEDCHAIN_EVM_CHAIN_ID),
        accounts: [process.env.MEDCHAIN_EVM_SIGNER_PRIVATE_KEY],
      },
    }
  : {};

const config = {
  solidity: {
    version: "0.8.28",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200
      }
    }
  },
  networks: {
    hardhat: {
      chainId: 31337
    },
    ...configuredNetwork,
  }
};

export default config;
