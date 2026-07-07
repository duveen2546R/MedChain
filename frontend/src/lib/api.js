export const API_BASE = import.meta.env.VITE_MEDCHAIN_API_URL || "http://localhost:8000";

const ACCESS_KEY = "medchain_token";
const REFRESH_KEY = "medchain_refresh";

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens({ access, refresh }) {
  if (access) localStorage.setItem(ACCESS_KEY, access);
  else localStorage.removeItem(ACCESS_KEY);
  if (refresh !== undefined) {
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    else localStorage.removeItem(REFRESH_KEY);
  }
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

/**
 * Thin fetch wrapper. Throws an ApiError (with .status and .detail) on non-2xx
 * so callers can surface backend validation messages to the user.
 */
export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function performRequest(path, init, token) {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  try {
    return await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach the MedChain backend. Is it running?");
  }
}

async function toJsonOrThrow(response) {
  if (!response.ok) {
    let detail;
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : undefined;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return null;
  return await response.json();
}

// Single-flight refresh: concurrent 401s share one /auth/refresh round-trip.
let refreshPromise = null;

function refreshAccessToken() {
  const refresh = getRefreshToken();
  if (!refresh) return Promise.resolve(null);
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const response = await performRequest("/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!response.ok) throw new ApiError(response.status);
        const res = await response.json();
        setTokens({ access: res.access_token, refresh: res.refresh_token });
        return res.access_token;
      } catch {
        clearTokens();
        window.dispatchEvent(new Event("medchain:logout"));
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}

export async function apiJson(path, init = {}, token) {
  const access = token ?? getAccessToken();
  let response = await performRequest(path, init, access);

  if (response.status === 401 && path !== "/auth/refresh" && getRefreshToken()) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      response = await performRequest(path, init, newAccess);
    }
  }

  return toJsonOrThrow(response);
}
