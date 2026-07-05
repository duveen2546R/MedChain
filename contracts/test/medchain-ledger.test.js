import { expect } from "chai";
import { ethers } from "hardhat";

describe("MedChain ledger contracts", function () {
  async function deployFixture() {
    const [owner, hospital, inactive] = await ethers.getSigners();

    const Registry = await ethers.getContractFactory("ConsortiumRegistry");
    const registry = await Registry.deploy();

    const Reputation = await ethers.getContractFactory("ReputationRegistry");
    const reputation = await Reputation.deploy();

    const Ledger = await ethers.getContractFactory("TrainingLedger");
    const ledger = await Ledger.deploy(await registry.getAddress(), await reputation.getAddress());
    await reputation.setTrainingLedger(await ledger.getAddress());

    const hospitalRole = ethers.id("hospital_node");
    await registry.registerNode(hospital.address, "org_h1", hospitalRole);
    await reputation.seedReputation(hospital.address, 92);

    return { owner, hospital, inactive, registry, reputation, ledger };
  }

  it("records a verified contribution and updates reputation", async function () {
    const { hospital, reputation, ledger } = await deployFixture();
    const roundId = ethers.id("rnd_1");
    const updateHash = ethers.id("update_1");

    await expect(
      ledger.recordContribution(roundId, "v1.1", hospital.address, updateHash, "ipfs://cid", true)
    )
      .to.emit(ledger, "ContributionRecorded")
      .withArgs(roundId, hospital.address, updateHash, "v1.1", "ipfs://cid", true);

    expect(await ledger.contributionCount()).to.equal(1);
    expect(await reputation.reputation(hospital.address)).to.equal(93);
  });

  it("rejects duplicate submissions for the same round and node", async function () {
    const { hospital, ledger } = await deployFixture();
    const roundId = ethers.id("rnd_1");

    await ledger.recordContribution(roundId, "v1.1", hospital.address, ethers.id("update_1"), "ipfs://cid-1", true);
    await expect(
      ledger.recordContribution(roundId, "v1.1", hospital.address, ethers.id("update_2"), "ipfs://cid-2", true)
    ).to.be.revertedWith("LEDGER_DUPLICATE_SUBMISSION");
  });

  it("rejects inactive or unregistered contributors", async function () {
    const { inactive, ledger } = await deployFixture();
    await expect(
      ledger.recordContribution(ethers.id("rnd_1"), "v1.1", inactive.address, ethers.id("update_1"), "ipfs://cid", true)
    ).to.be.revertedWith("LEDGER_INACTIVE_NODE");
  });

  it("reduces reputation for rejected updates", async function () {
    const { hospital, reputation, ledger } = await deployFixture();
    await ledger.recordContribution(ethers.id("rnd_1"), "v1.1", hospital.address, ethers.id("update_1"), "ipfs://cid", false);
    expect(await reputation.reputation(hospital.address)).to.equal(88);
  });
});
