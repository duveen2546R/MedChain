import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { apiJson } from "./api";

const TOKEN_KEY = "medchain_token";
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

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(localStorage.getItem(TOKEN_KEY)));
  const tokenRef = useRef(token);
  tokenRef.current = token;

  const persistToken = useCallback((value) => {
    tokenRef.current = value;
    setToken(value);
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  }, []);

  const logout = useCallback(() => {
    persistToken(null);
    setUser(null);
  }, [persistToken]);

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
          persistToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [persistToken]);

  const login = useCallback(
    async (email, password) => {
      const res = await apiJson("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      persistToken(res.access_token);
      const me = await apiJson("/me", {}, res.access_token);
      setUser(me);
      return me;
    },
    [persistToken]
  );

  const register = useCallback(
    async (payload) => {
      const res = await apiJson("/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      persistToken(res.access_token);
      const me = await apiJson("/me", {}, res.access_token);
      setUser(me);
      return me;
    },
    [persistToken]
  );

  const value = useMemo(
    () => ({ token, user, loading, login, register, logout, isAuthenticated: Boolean(token && user) }),
    [token, user, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
