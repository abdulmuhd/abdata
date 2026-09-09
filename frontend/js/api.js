// Session state + API client with automatic token refresh.
const SESSION_KEY = "zaply.session.v1";
const API_BASE_KEY = "zaply.api.base";

// Point the app at a website's API once with  /?api=https://your-site.com
// (persisted for later visits). Empty base = same origin as this page.
try {
  const qsApi = new URLSearchParams(location.search).get("api");
  if (qsApi !== null) localStorage.setItem(API_BASE_KEY, qsApi.trim().replace(/\/+$/, ""));
} catch { /* storage unavailable */ }
const API_BASE = (() => {
  try { return localStorage.getItem(API_BASE_KEY) || ""; } catch { return ""; }
})();

export const apiBase = () => API_BASE;

export const store = {
  session: null, // { access_token, refresh_token }
  user: null,
  balanceKobo: 0,
  bonusKobo: 0,
  unread: 0,
};

export function loadSession() {
  try {
    store.session = JSON.parse(localStorage.getItem(SESSION_KEY));
  } catch {
    store.session = null;
  }
}

export function saveSession(pair) {
  store.session = pair;
  localStorage.setItem(SESSION_KEY, JSON.stringify(pair));
  localStorage.setItem(SESSION_KEY + ".ts", String(Date.now()));
}

const MAX_SESSION_MS = 24 * 60 * 60 * 1000; // 24 hours

export function isSessionExpired() {
  try {
    const ts = Number(localStorage.getItem(SESSION_KEY + ".ts") || 0);
    return ts > 0 && Date.now() - ts > MAX_SESSION_MS;
  } catch { return false; }
}

export function clearSession() {
  store.session = null;
  store.user = null;
  localStorage.removeItem(SESSION_KEY);
}

export class ApiError extends Error {
  constructor(status, payload) {
    super(payload?.message || "Something went wrong. Please try again.");
    this.status = status;
    this.code = payload?.code || "error";
    this.payload = payload;
  }
}

let refreshing = null;

async function rawRequest(method, path, body, auth = true) {
  const headers = { "Content-Type": "application/json" };
  if (auth && store.session?.access_token) {
    headers.Authorization = `Bearer ${store.session.access_token}`;
  }
  let res;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // network-level failure: unreachable host, refused connection, CORS block…
    throw new ApiError(0, {
      message:
        `Can't reach the Zaply server${API_BASE ? ` at ${API_BASE}` : ""}. ` +
        "Check your connection" +
        (API_BASE
          ? ` — this page is pinned to a custom API; open it with ?api= (empty value resets to same-origin).`
          : " and make sure the backend is running."),
      code: "network_error",
    });
  }
  let payload = null;
  try {
    payload = await res.json();
  } catch {
    /* empty body */
  }
  return { res, payload };
}

async function refreshTokens() {
  if (!refreshing) {
    refreshing = (async () => {
      const { res, payload } = await rawRequest("POST", "/auth/refresh", {
        refresh_token: store.session?.refresh_token || "",
      }, false);
      if (!res.ok) throw new ApiError(res.status, payload);
      saveSession({ access_token: payload.data.access_token, refresh_token: payload.data.refresh_token });
      return payload.data;
    })().finally(() => { setTimeout(() => { refreshing = null; }, 50); });
  }
  return refreshing;
}

export async function api(method, path, body, { auth = true, retry = true } = {}) {
  const { res, payload } = await rawRequest(method, path, body, auth);

  if (res.status === 401 && auth && retry && store.session?.refresh_token) {
    try {
      await refreshTokens();
      return api(method, path, body, { auth, retry: false });
    } catch {
      clearSession();
      location.hash = "#/welcome";
      throw new ApiError(401, { message: "Session expired. Please sign in again." });
    }
  }
  if (!res.ok) throw new ApiError(res.status, payload);
  return payload?.data ?? payload;
}

export const get = (p) => api("GET", p);
export const post = (p, b) => api("POST", p, b);
export const patch = (p, b) => api("PATCH", p, b);
export const put = (p, b) => api("PUT", p, b);
