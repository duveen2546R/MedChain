import { useCallback, useEffect, useState } from "react";
import { ApiError, apiJson } from "./api";
import { useAuth } from "./auth";

const EMPTY_SUMMARY = {
  hospitals: [],
  versions: [],
  round: 0,
  currentRoundId: null,
  currentRoundStatus: null,
  running: false,
  phase: "Connecting to backend",
  activeNode: null,
  submissionsReceived: 0,
  submissionsRequired: 0,
  blockchainTransactions: 0,
  blockchainChainId: null,
  blockchainConnected: false,
  blockchainSigner: null,
};

export function useFederatedBackend() {
  const { token } = useAuth();
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [backendConnected, setBackendConnected] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [pendingAction, setPendingAction] = useState("");

  const refresh = useCallback(async () => {
    try {
      const nextSummary = await apiJson("/dashboard/summary", {}, token);
      setSummary(nextSummary);
      setBackendConnected(true);
      setRequestError("");
      return nextSummary;
    } catch (error) {
      setBackendConnected(false);
      setRequestError(error instanceof ApiError ? error.message : "Backend request failed");
      return null;
    }
  }, [token]);

  useEffect(() => {
    if (!token) return undefined;
    void refresh();
    const interval = window.setInterval(refresh, 3000);
    return () => window.clearInterval(interval);
  }, [refresh, token]);

  const runRound = useCallback(async () => {
    try {
      setRequestError("");
      setPendingAction("round:create");
      await apiJson(
        "/rounds",
        { method: "POST", body: JSON.stringify({}) },
        token,
      );
      await refresh();
    } catch (error) {
      setRequestError(error instanceof ApiError ? error.message : "Failed to create training round");
    } finally {
      setPendingAction("");
    }
  }, [refresh, token]);

  const registerHospitalOnChain = useCallback(async (hospitalId) => {
    try {
      setRequestError("");
      setPendingAction(`hospital:${hospitalId}:register`);
      await apiJson(
        `/hospitals/${hospitalId}/blockchain/register`,
        { method: "POST" },
        token,
      );
      await refresh();
    } catch (error) {
      setRequestError(error instanceof ApiError ? error.message : "Failed to register hospital on-chain");
    } finally {
      setPendingAction("");
    }
  }, [refresh, token]);

  const retryRoundBlockchain = useCallback(async () => {
    if (!summary.currentRoundId) return;
    try {
      setRequestError("");
      setPendingAction(`round:${summary.currentRoundId}:retry-chain`);
      await apiJson(
        `/rounds/${summary.currentRoundId}/blockchain/retry`,
        { method: "POST" },
        token,
      );
      await refresh();
    } catch (error) {
      setRequestError(error instanceof ApiError ? error.message : "Failed to retry blockchain recording");
    } finally {
      setPendingAction("");
    }
  }, [refresh, summary.currentRoundId, token]);

  return {
    ...summary,
    backendConnected,
    phase: requestError || summary.phase,
    pendingAction,
    runRound,
    registerHospitalOnChain,
    retryRoundBlockchain,
  };
}
