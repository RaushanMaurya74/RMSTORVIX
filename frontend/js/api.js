/**
 * Modular HTTP API client for the Invoice & Billing System.
 */

const API_ORIGIN = (
  typeof window !== "undefined" && window.__RMSTORVIX_CONFIG__?.apiBaseUrl
    ? String(window.__RMSTORVIX_CONFIG__.apiBaseUrl)
    : ""
).replace(/\/+$/, "");
const API_BASE = `${API_ORIGIN}/api/v1`;
const FETCH_CREDENTIALS = API_ORIGIN ? "include" : "same-origin";

export class ApiError extends Error {
  constructor(message, status, details = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function apiRequest(path, options = {}) {
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
    const errorBody = payload?.error;
    let message =
      errorBody?.message ||
      (typeof payload?.detail === "string" ? payload.detail : "") ||
      `Request failed (${response.status}).`;
    const details = Array.isArray(errorBody?.details) ? errorBody.details : [];
    if (details.length > 0 && details[0]?.message) {
      message = `${message} ${details[0].message}`;
    }
    throw new ApiError(message, response.status, details);
  }

  return payload;
}

function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchSystemHealth() {
  const response = await fetch(`${API_BASE}/health`, {
    method: "GET",
    credentials: FETCH_CREDENTIALS,
    headers: { Accept: "application/json" },
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!payload || typeof payload !== "object") {
    throw new Error(`Health check returned unexpected status (${response.status}).`);
  }

  return { httpStatus: response.status, data: payload };
}

export async function fetchCurrentSession() {
  return apiRequest("/auth/me", { method: "GET" });
}

export async function registerAccount(payload) {
  return apiRequest("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function loginAccount(payload) {
  return apiRequest("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function logoutAccount() {
  return apiRequest("/auth/logout", { method: "POST" });
}

export async function forgotPasswordRequest(payload) {
  return apiRequest("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function changeUserPassword(payload) {
  return apiRequest("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchSaasSupport() {
  return apiRequest("/saas/support", { method: "GET" });
}

export async function fetchSubscriptionStatus() {
  return apiRequest("/subscription", { method: "GET" });
}

export async function activateSubscriptionCode(code) {
  return apiRequest("/subscription/activate", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}

export async function fetchBusinessNotifications() {
  return apiRequest("/notifications", { method: "GET" });
}

export async function markBusinessNotificationRead(notificationId) {
  return apiRequest(`/notifications/${notificationId}/read`, { method: "POST" });
}

export async function markAllBusinessNotificationsRead() {
  return apiRequest("/notifications/read-all", { method: "POST" });
}

export async function fetchBusinessProfile() {
  return apiRequest("/business", { method: "GET" });
}

export async function updateBusinessProfile(payload) {
  return apiRequest("/business", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

async function uploadMultipart(path, file, { method = "POST", fallbackMessage = "Upload failed" } = {}) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: FETCH_CREDENTIALS,
    headers: { Accept: "application/json" },
    body: formData,
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.error?.message || `${fallbackMessage} (${response.status}).`;
    throw new ApiError(message, response.status, payload?.error?.details || []);
  }
  return payload;
}

export function getBusinessSignatureUrl() {
  return `${API_BASE}/business/signature`;
}

export async function uploadBusinessSignature(file) {
  return uploadMultipart("/business/signature", file, {
    method: "POST",
    fallbackMessage: "Signature upload failed",
  });
}

export async function removeBusinessSignature() {
  return apiRequest("/business/signature", { method: "DELETE" });
}

export function getBusinessLogoUrl() {
  return `${API_BASE}/business/logo`;
}

export async function uploadBusinessLogo(file, isReplace = false) {
  return uploadMultipart("/business/logo", file, {
    method: isReplace ? "PUT" : "POST",
    fallbackMessage: "Logo upload failed",
  });
}

export async function removeBusinessLogo() {
  return apiRequest("/business/logo", { method: "DELETE" });
}

export async function fetchBusinessAppearance() {
  return apiRequest("/business/appearance", { method: "GET" });
}

export async function fetchInvoiceTheme() {
  return apiRequest("/business/theme", { method: "GET" });
}

export async function updateInvoiceTheme(payload) {
  return apiRequest("/business/theme", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function fetchCustomers(params) {
  return apiRequest(`/customers${buildQuery(params)}`, { method: "GET" });
}

export async function verifyCustomerGstin(gstin) {
  return apiRequest("/customers/verify-gstin", {
    method: "POST",
    body: JSON.stringify({ gstin }),
  });
}

export async function createCustomer(payload) {
  return apiRequest("/customers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateCustomer(customerId, payload) {
  return apiRequest(`/customers/${customerId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteCustomer(customerId) {
  return apiRequest(`/customers/${customerId}`, { method: "DELETE" });
}

export async function fetchProducts(params) {
  return apiRequest(`/products${buildQuery(params)}`, { method: "GET" });
}

export async function createProduct(payload) {
  return apiRequest("/products", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateProduct(productId, payload) {
  return apiRequest(`/products/${productId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function adjustProductStock(productId, payload) {
  return apiRequest(`/products/${productId}/adjust-stock`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteProduct(productId) {
  return apiRequest(`/products/${productId}`, { method: "DELETE" });
}

export async function fetchInvoices(params) {
  return apiRequest(`/invoices${buildQuery(params)}`, { method: "GET" });
}

export async function fetchInvoice(invoiceId) {
  return apiRequest(`/invoices/${invoiceId}`, { method: "GET" });
}

export async function createInvoice(payload) {
  return apiRequest("/invoices", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateInvoice(invoiceId, payload) {
  return apiRequest(`/invoices/${invoiceId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function issueInvoice(invoiceId) {
  return apiRequest(`/invoices/${invoiceId}/issue`, { method: "POST" });
}

export async function duplicateInvoice(invoiceId) {
  return apiRequest(`/invoices/${invoiceId}/duplicate`, { method: "POST" });
}

export async function voidInvoice(invoiceId, reason = null) {
  return apiRequest(`/invoices/${invoiceId}/void`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export async function deleteInvoice(invoiceId) {
  return apiRequest(`/invoices/${invoiceId}`, { method: "DELETE" });
}

export function getInvoicePdfUrl(invoiceId, disposition = "attachment") {
  return `${API_BASE}/invoices/${invoiceId}/pdf?disposition=${encodeURIComponent(disposition)}`;
}

export function getInvoiceQrUrl(invoiceId) {
  return `${API_BASE}/invoices/${invoiceId}/qr`;
}

export async function fetchPayments(params) {
  return apiRequest(`/payments${buildQuery(params)}`, { method: "GET" });
}

export async function recordPayment(payload) {
  return apiRequest("/payments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deletePayment(paymentId) {
  return apiRequest(`/payments/${paymentId}`, { method: "DELETE" });
}

export async function fetchSalesSummary(params) {
  return apiRequest(`/reports/summary${buildQuery(params)}`, { method: "GET" });
}

export function getInvoicesCsvUrl(params) {
  return `${API_BASE}/reports/invoices.csv${buildQuery(params)}`;
}

export async function fetchAuditEvents(params) {
  return apiRequest(`/reports/audit${buildQuery(params)}`, { method: "GET" });
}
