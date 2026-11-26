/**
 * HTTP API client strictly scoped to RMSTORVIX Administrator Control Plane (/api/v1/admin/*).
 */

const API_ORIGIN = (
  typeof window !== "undefined" && window.__RMSTORVIX_CONFIG__?.apiBaseUrl
    ? String(window.__RMSTORVIX_CONFIG__.apiBaseUrl)
    : ""
).replace(/\/+$/, "");
const API_BASE = `${API_ORIGIN}/api/v1/admin`;
const FETCH_CREDENTIALS = API_ORIGIN ? "include" : "same-origin";

export class AdminApiError extends Error {
  constructor(message, status, details = []) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
    this.details = details;
  }
}

function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") {
      search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

async function adminRequest(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: FETCH_CREDENTIALS,
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

  if (response.status === 204) {
    return null;
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const errObj = payload?.error;
    let msg =
      errObj?.message ||
      (typeof payload?.detail === "string" ? payload.detail : "") ||
      `Request failed (${response.status}).`;
    const details = Array.isArray(errObj?.details) ? errObj.details : [];
    if (details.length > 0 && details[0]?.message) {
      msg = `${msg} ${details[0].message}`;
    }
    throw new AdminApiError(msg, response.status, details);
  }

  return payload;
}

// --- Admin Auth ---
export function adminLogin(payload) {
  return adminRequest("/auth/login", { method: "POST", body: JSON.stringify(payload) });
}

export function adminLogout() {
  return adminRequest("/auth/logout", { method: "POST" });
}

export function fetchAdminMe() {
  return adminRequest("/auth/me", { method: "GET" });
}

export function changeAdminPassword(payload) {
  return adminRequest("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// --- Overview ---
export function fetchAdminOverview() {
  return adminRequest("/overview", { method: "GET" });
}

// --- Users & Approvals ---
export function fetchAdminUsers(params) {
  return adminRequest(`/users${buildQuery(params)}`, { method: "GET" });
}

export function fetchAdminUserDetail(userId) {
  return adminRequest(`/users/${userId}`, { method: "GET" });
}

export function approveAdminUser(userId, payload = {}) {
  return adminRequest(`/users/${userId}/approve`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function rejectAdminUser(userId, payload = {}) {
  return adminRequest(`/users/${userId}/reject`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function activateAdminUser(userId, payload = {}) {
  return adminRequest(`/users/${userId}/activate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deactivateAdminUser(userId, payload = {}) {
  return adminRequest(`/users/${userId}/deactivate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function suspendAdminUser(userId, payload = {}) {
  return adminRequest(`/users/${userId}/suspend`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function reactivateAdminUser(userId, payload = {}) {
  return adminRequest(`/users/${userId}/reactivate`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function editAdminUserBusiness(userId, payload) {
  return adminRequest(`/users/${userId}/business`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function resetAdminUserPassword(userId, payload) {
  return adminRequest(`/users/${userId}/reset-password`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteAdminUser(userId) {
  return adminRequest(`/users/${userId}`, { method: "DELETE" });
}

// --- Plans ---
export function fetchAdminPlans(includeInactive = true) {
  return adminRequest(`/plans${buildQuery({ include_inactive: includeInactive })}`, {
    method: "GET",
  });
}

export function createAdminPlan(payload) {
  return adminRequest("/plans", { method: "POST", body: JSON.stringify(payload) });
}

export function updateAdminPlan(planId, payload) {
  return adminRequest(`/plans/${planId}`, { method: "PUT", body: JSON.stringify(payload) });
}

// --- Subscriptions ---
export function fetchAdminSubscriptions(params) {
  return adminRequest(`/subscriptions${buildQuery(params)}`, { method: "GET" });
}

export function assignUserSubscription(userId, payload) {
  return adminRequest(`/users/${userId}/subscription`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function extendAdminSubscription(subscriptionId, payload) {
  return adminRequest(`/subscriptions/${subscriptionId}/extend`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAdminSubscriptionStatus(subscriptionId, payload) {
  return adminRequest(`/subscriptions/${subscriptionId}/status`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

// --- Activation Codes ---
export function fetchAdminCodes(params) {
  return adminRequest(`/activation-codes${buildQuery(params)}`, { method: "GET" });
}

export function getAdminCodesExportUrl(statusFilter = "") {
  return `${API_BASE}/activation-codes/export.csv${buildQuery({ status: statusFilter })}`;
}

export function generateAdminCodes(payload) {
  return adminRequest("/activation-codes", { method: "POST", body: JSON.stringify(payload) });
}

export function assignAdminCode(codeId, userId) {
  return adminRequest(`/activation-codes/${codeId}/assign`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export function revokeAdminCode(codeId, reason = "") {
  return adminRequest(`/activation-codes/${codeId}/revoke`, {
    method: "POST",
    body: JSON.stringify({ reason: reason || null }),
  });
}

export function redeemAdminCodeForUser(codeId, userId, extendExisting = true) {
  return adminRequest(`/activation-codes/${codeId}/activate`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId, extend_existing: extendExisting }),
  });
}

// --- Notifications, Audit & Settings ---
export function fetchAdminNotifications() {
  return adminRequest("/notifications", { method: "GET" });
}

export function markAdminNotificationRead(id) {
  return adminRequest(`/notifications/${id}/read`, { method: "POST" });
}

export function markAllAdminNotificationsRead() {
  return adminRequest("/notifications/read-all", { method: "POST" });
}

export function fetchAdminAuditLogs(params) {
  return adminRequest(`/audit-logs${buildQuery(params)}`, { method: "GET" });
}

export function fetchAdminSettings() {
  return adminRequest("/settings", { method: "GET" });
}

export function saveAdminSettings(payload) {
  return adminRequest("/settings", { method: "PUT", body: JSON.stringify(payload) });
}
