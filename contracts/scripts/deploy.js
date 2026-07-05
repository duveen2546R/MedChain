import hre from "hardhat";

const { ethers } = hre;

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`Deploying MedChain contracts from ${deployer.address}`);

  const registry = await ethers.deployContract("ConsortiumRegistry");
  await registry.waitForDeployment();

  const reputation = await ethers.deployContract("ReputationRegistry");
  await reputation.waitForDeployment();

  const ledger = await ethers.deployContract("TrainingLedger", [
    await registry.getAddress(),
    await reputation.getAddress(),
  ]);
  await ledger.waitForDeployment();

  const setLedger = await reputation.setTrainingLedger(await ledger.getAddress());
  await setLedger.wait();

  const network = await ethers.provider.getNetwork();
  console.log(`MEDCHAIN_EVM_CHAIN_ID=${network.chainId}`);
  console.log(`MEDCHAIN_CONSORTIUM_REGISTRY_ADDRESS=${await registry.getAddress()}`);
  console.log(`MEDCHAIN_REPUTATION_REGISTRY_ADDRESS=${await reputation.getAddress()}`);
  console.log(`MEDCHAIN_TRAINING_LEDGER_ADDRESS=${await ledger.getAddress()}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
