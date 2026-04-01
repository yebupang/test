const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "请求失败");
  }
  return res.json();
}

// ─── Portfolio ────────────────────────────────────────────
export const getPortfolioSummary = () => request("/portfolio/summary");
export const getPositions = (params?: { market?: string; account_id?: number }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return request(`/portfolio/positions${qs ? `?${qs}` : ""}`);
};
export const updatePosition = (id: number, data: { position_type?: string }) =>
  request(`/portfolio/positions/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

// ─── Accounts ─────────────────────────────────────────────
export const getAccounts = () => request("/accounts/");
export const createAccount = (data: object) =>
  request("/accounts/", { method: "POST", body: JSON.stringify(data) });

// ─── Sync ─────────────────────────────────────────────────
export const syncFutu = (accountId: number) =>
  request(`/sync/futu/${accountId}`, { method: "POST" });
export const syncIB = (accountId: number) =>
  request(`/sync/ib/${accountId}`, { method: "POST" });
export const syncMock = (accountId: number) =>
  request(`/sync/mock/${accountId}`, { method: "POST" });
export const refreshQuotes = (accountId?: number) =>
  request(`/sync/quotes/refresh${accountId ? `?account_id=${accountId}` : ""}`, {
    method: "POST",
  });
export const getSyncLogs = () => request("/sync/logs");

export const syncCSV = async (accountId: number, file: File) => {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/sync/csv/${accountId}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("CSV 上传失败");
  return res.json();
};

// ─── Watchlist ────────────────────────────────────────────
export const getWatchlist = () => request("/watchlist/");
export const addToWatchlist = (data: object) =>
  request("/watchlist/", { method: "POST", body: JSON.stringify(data) });
export const updateWatchlistItem = (id: number, data: object) =>
  request(`/watchlist/${id}`, { method: "PATCH", body: JSON.stringify(data) });
export const removeFromWatchlist = (id: number) =>
  request(`/watchlist/${id}`, { method: "DELETE" });
