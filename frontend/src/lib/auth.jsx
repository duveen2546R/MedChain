import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiJson, clearTokens, getAccessToken, setTokens } from "./api";

const AuthContext = createContext(null);

const ROLE_LABELS = {
  platform_admin: "Platform Admin",
  hospital_admin: "Hospital Admin",
  hospital_node: "Hospital Node",
  clinic_user: "Clinic",
  auditor: "Auditor",
  research_partner: "Research Partner",
};

export function roleLabel(role) {
  return ROLE_LABELS[role] || role || "Member";
}

// Roles allowed to start training rounds (mirrors backend RBAC).
export function canRunRounds(role) {
  return role === "platform_admin" || role === "hospital_admin";
}

// Roles allowed to manage invitations / access requests (mirrors backend RBAC).
export function canManageTeam(role) {
  return role === "platform_admin" || role === "hospital_admin";
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => getAccessToken());
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getAccessToken()));
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const persistTokens = useCallback((access, refresh) => {
    tokenRef.current = access;
    setToken(access);
    setTokens({ access, refresh });
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    tokenRef.current = null;
    setToken(null);
    setUser(null);
  }, []);

  // If a background refresh fails, api.js dispatches this so React state clears too.
  useEffect(() => {
    const onForcedLogout = () => {
      tokenRef.current = null;
      setToken(null);
      setUser(null);
    };
    window.addEventListener("medchain:logout", onForcedLogout);
    return () => window.removeEventListener("medchain:logout", onForcedLogout);
  }, []);

  // Hydrate the user from an existing token on first load.
  useEffect(() => {
    let cancelled = false;
    const stored = tokenRef.current;
    if (!stored) {
      setLoading(false);
      return undefined;
    }
    (async () => {
      try {
        const me = await apiJson("/me", {}, stored);
        if (!cancelled) setUser(me);
      } catch {
        if (!cancelled) {
          logout();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [logout]);

  const finishAuth = useCallback(
    async (res) => {
      persistTokens(res.access_token, res.refresh_token);
      const me = await apiJson("/me", {}, res.access_token);
      setUser(me);
      return me;
    },
    [persistTokens]
  );

  const login = useCallback(
    async (email, password) => {
      const res = await apiJson("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      return finishAuth(res);
    },
    [finishAuth]
  );

  const acceptInvite = useCallback(
    async (inviteToken, name, password) => {
      const res = await apiJson("/auth/register", {
        method: "POST",
        body: JSON.stringify({ token: inviteToken, name, password }),
      });
      return finishAuth(res);
    },
    [finishAuth]
  );

  const requestAccess = useCallback(
    (payload) =>
      apiJson("/auth/access-requests", { method: "POST", body: JSON.stringify(payload) }),
    []
  );

  const forgotPassword = useCallback(
    (email) =>
      apiJson("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
    []
  );

  const resetPassword = useCallback(
    (resetToken, password) =>
      apiJson("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token: resetToken, password }),
      }),
    []
  );

  const value = useMemo(
    () => ({
      token,
      user,
      loading,
      login,
      acceptInvite,
      requestAccess,
      forgotPassword,
      resetPassword,
      logout,
      isAuthenticated: Boolean(token && user),
    }),
    [token, user, loading, login, acceptInvite, requestAccess, forgotPassword, resetPassword, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
