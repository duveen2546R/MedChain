import { useCallback, useEffect, useState } from "react";
import { ApiError, apiJson } from "./api";
import { useAuth } from "./auth";

const EMPTY_SUMMARY = {
  hospitals: [],
  versions: [],
  round: 0,
  running: false,
  phase: "Connecting to backend",
  activeNode: null,
  submissionsReceived: 0,
  submissionsRequired: 0,
};

export function useFederatedBackend() {
  const { token } = useAuth();
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [backendConnected, setBackendConnected] = useState(false);
  const [requestError, setRequestError] = useState("");

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
      await apiJson(
        "/rounds",
        { method: "POST", body: JSON.stringify({}) },
        token,
      );
      await refresh();
    } catch (error) {
      setRequestError(error instanceof ApiError ? error.message : "Failed to create training round");
    }
  }, [refresh, token]);

  return {
    ...summary,
    backendConnected,
    phase: requestError || summary.phase,
    runRound,
  };
}
