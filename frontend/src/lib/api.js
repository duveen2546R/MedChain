export const API_BASE = import.meta.env.VITE_MEDCHAIN_API_URL || "http://localhost:8000";

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

export async function apiJson(path, init = {}, token) {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Can't reach the MedChain backend. Is it running?");
  }

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
