/**
 * Application shell bootstrapper: authentication gate, navigation, and business modules.
 */

import {
  ApiError,
  fetchBusinessAppearance,
  fetchBusinessProfile,
  fetchCurrentSession,
  fetchCustomers,
  fetchInvoices,
  fetchProducts,
  fetchSaasSupport,
  fetchSalesSummary,
  fetchSystemHealth,
  getBusinessLogoUrl,
  loginAccount,
  logoutAccount,
  registerAccount,
  removeBusinessLogo,
  removeBusinessSignature,
  updateBusinessProfile,
  updateInvoiceTheme,
  uploadBusinessLogo,
  uploadBusinessSignature,
} from "/js/api.js";
import { renderAccountGateScreen, renderSaasAuthScreen } from "/js/authView.js";
import { showToast } from "/js/dom.js";
import { createCustomersController } from "/js/customersView.js";
import { createInventoryController } from "/js/inventoryView.js";
import { createInvoicesController } from "/js/invoicesView.js";
import { createNotificationsController } from "/js/notificationsView.js";
import { createPaymentsController } from "/js/paymentsView.js";
import { createProductsController } from "/js/productsView.js";
import { createReportsController } from "/js/reportsView.js";
import { createSubscriptionController } from "/js/subscriptionView.js";
import {
  getSectionTitle,
  renderHealthPill,
  renderSection,
} from "/js/ui.js";

const state = {
  activeSection: "dashboard",
  session: null,
  counts: {
    customers: null,
    products: null,
    invoices: null,
    recentInvoices: [],
    summary: null,
  },
  authUi: {
    mode: "login",
    loading: false,
    error: null,
  },
  settingsUi: {
    saving: false,
    uploadingSignature: false,
    uploadingLogo: false,
    savingTheme: false,
    error: null,
    success: null,
  },
  themePresets: [],
  supportInfo: null,
  health: {
    loading: true,
    result: null,
    error: null,
  },
};

const SIDEBAR_STORAGE_KEY = "inv_sidebar_collapsed";
const THEME_STORAGE_KEY = "inv_color_theme";
const VALID_SECTIONS = new Set([
  "dashboard",
  "invoices",
  "customers",
  "products",
  "inventory",
  "payments",
  "reports",
  "notifications",
  "subscription",
  "activation",
  "settings",
]);
const mobileMediaQuery = window.matchMedia("(max-width: 768px)");
let eventsBound = false;

const sidebarState = {
  mobileOpen: false,
  desktopCollapsed: (() => {
    try {
      return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  })(),
};

const elements = {
  authShell: document.getElementById("auth-shell"),
  appShell: document.getElementById("app-shell"),
  sidebar: document.getElementById("app-sidebar"),
  backdrop: document.getElementById("sidebar-backdrop"),
  menuToggleBtn: document.getElementById("menu-toggle-btn"),
  sidebarCloseBtn: document.getElementById("sidebar-close-btn"),
  brandLogoImg: document.getElementById("brand-logo-img"),
  brandFallbackMark: document.getElementById("brand-fallback-mark"),
  topbarLogoImg: document.getElementById("topbar-logo-img"),
  sidebarBusinessName: document.getElementById("sidebar-business-name"),
  sidebarUserEmail: document.getElementById("sidebar-user-email"),
  navButtons: Array.from(document.querySelectorAll(".nav-item-btn")),
  topbarTitle: document.getElementById("topbar-title"),
  mainContent: document.getElementById("main-content"),
  healthRefreshBtn: document.getElementById("health-refresh-btn"),
  healthPillText: document.getElementById("health-pill-text"),
  themeModeToggle: document.getElementById("theme-mode-toggle"),
  newInvoiceBtn: document.getElementById("new-invoice-btn"),
  signOutBtn: document.getElementById("sign-out-btn"),
};

function getColorTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function syncThemeToggleUi() {
  const current = getColorTheme();
  const isDark = current === "dark";
  if (elements.themeModeToggle) {
    elements.themeModeToggle.setAttribute("aria-pressed", String(isDark));
    elements.themeModeToggle.setAttribute(
      "aria-label",
      isDark ? "Switch to bright mode" : "Switch to dark mode"
    );
    elements.themeModeToggle.title = isDark ? "Switch to bright mode" : "Switch to dark mode";
  }
}

function applyColorTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  document.documentElement.style.colorScheme = next;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // Ignore storage errors in restricted browsing modes.
  }
  syncThemeToggleUi();
  if (!state.session) {
    renderActiveView();
  }
}

function toggleColorTheme() {
  applyColorTheme(getColorTheme() === "dark" ? "light" : "dark");
}

function parseRouteFromLocation() {
  const rawHash = (window.location.hash || "").replace(/^#\/?/, "").trim();
  const rawPath = (window.location.pathname || "/").replace(/^\/+|\/+$/g, "").trim();
  const candidate = rawHash || rawPath;
  if (!candidate || candidate === "index.html") {
    return "dashboard";
  }
  if (candidate === "invoices/new" || candidate === "invoices-new") {
    return "invoices-new";
  }
  const invMatch = /^invoices\/(\d+)$/.exec(candidate);
  if (invMatch) {
    return `invoice:${invMatch[1]}`;
  }
  const base = candidate.split("/")[0];
  return VALID_SECTIONS.has(base) ? base : "dashboard";
}

function routeKeyToHash(routeKey) {
  if (routeKey === "invoices-new") return "#/invoices/new";
  if (typeof routeKey === "string" && routeKey.startsWith("invoice:")) {
    return `#/invoices/${routeKey.split(":")[1]}`;
  }
  return VALID_SECTIONS.has(routeKey) ? `#/${routeKey}` : "#/dashboard";
}

function handleAuthExpired() {
  state.session = null;
  state.counts = {
    customers: null,
    products: null,
    invoices: null,
    recentInvoices: [],
    summary: null,
  };
  renderActiveView();
}

const customersController = createCustomersController({
  onAuthExpired: handleAuthExpired,
  onCountsChanged: () => {
    void refreshDashboardCounts();
  },
});

const productsController = createProductsController({
  getCurrencyCode: () => state.session?.business?.currency_code || "USD",
  onAuthExpired: handleAuthExpired,
  onCountsChanged: () => {
    void refreshDashboardCounts();
  },
});

const invoicesController = createInvoicesController({
  getBusiness: () => state.session?.business,
  onAuthExpired: handleAuthExpired,
  onInvoicesChanged: () => {
    void refreshDashboardCounts();
  },
});

const paymentsController = createPaymentsController({
  onAuthExpired: handleAuthExpired,
  onPaymentsChanged: () => {
    void refreshDashboardCounts();
  },
  onOpenInvoice: (invoiceId) => {
    void navigateTo(`invoice:${invoiceId}`);
  },
});

const reportsController = createReportsController({
  onAuthExpired: handleAuthExpired,
});

const inventoryController = createInventoryController({
  getCurrencyCode: () => state.session?.business?.currency_code || "USD",
  onAuthExpired: handleAuthExpired,
  onInventoryChanged: () => {
    void refreshDashboardCounts();
  },
});

const notificationsController = createNotificationsController({
  onAuthExpired: handleAuthExpired,
  onNavigate: (target) => {
    void navigateTo(target);
  },
});

const subscriptionController = createSubscriptionController({
  getSupportInfo: () => state.supportInfo,
  onAuthExpired: handleAuthExpired,
  onSubscriptionUpdated: (updatedSub) => {
    if (state.session) {
      state.session = {
        ...state.session,
        subscription: updatedSub,
        business: state.session.business
          ? { ...state.session.business, subscription_status: updatedSub.status }
          : state.session.business,
      };
    }
  },
  onNavigate: (target) => {
    void navigateTo(target);
  },
});

function canAccessWorkspace(session) {
  if (!session) return false;
  const approval = session.user?.approval_status || "PENDING_APPROVAL";
  const subStatus = session.subscription?.status || session.business?.subscription_status || "NOT_ACTIVATED";
  if (approval !== "ACTIVE" && approval !== "APPROVED") return false;
  if (subStatus === "NOT_ACTIVATED" || subStatus === "SUSPENDED" || subStatus === "CANCELLED") {
    return false;
  }
  return true;
}

function isMobileViewport() {
  return mobileMediaQuery.matches || window.innerWidth <= 768;
}

function syncSidebarUi() {
  const isMobile = isMobileViewport();
  if (isMobile) {
    elements.appShell.classList.remove("sidebar-collapsed");
    elements.sidebar.classList.toggle("is-open", sidebarState.mobileOpen);
    elements.backdrop.classList.toggle("is-visible", sidebarState.mobileOpen);
    elements.backdrop.setAttribute("aria-hidden", String(!sidebarState.mobileOpen));
    document.body.classList.toggle("drawer-open", sidebarState.mobileOpen);
    elements.menuToggleBtn.setAttribute("aria-expanded", String(sidebarState.mobileOpen));
  } else {
    elements.sidebar.classList.remove("is-open");
    elements.backdrop.classList.remove("is-visible");
    elements.backdrop.setAttribute("aria-hidden", "true");
    document.body.classList.remove("drawer-open");
    elements.appShell.classList.toggle("sidebar-collapsed", sidebarState.desktopCollapsed);
    elements.menuToggleBtn.setAttribute("aria-expanded", String(!sidebarState.desktopCollapsed));
  }
}

function setDrawerOpen(isOpen) {
  sidebarState.mobileOpen = Boolean(isOpen);
  syncSidebarUi();
}

function toggleSidebar() {
  if (isMobileViewport()) {
    setDrawerOpen(!sidebarState.mobileOpen);
  } else {
    sidebarState.desktopCollapsed = !sidebarState.desktopCollapsed;
    try {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarState.desktopCollapsed));
    } catch {
      // Ignore storage errors in restricted browsing modes.
    }
    syncSidebarUi();
  }
}

function updateHeaderBusinessBranding(business) {
  const hasLogo = Boolean(business?.has_logo);
  if (hasLogo) {
    const logoSrc = `${getBusinessLogoUrl()}?v=${encodeURIComponent(business.logo_updated_at || "")}`;
    if (elements.brandLogoImg) {
      elements.brandLogoImg.src = logoSrc;
      elements.brandLogoImg.classList.remove("is-hidden");
    }
    elements.brandFallbackMark?.classList.add("is-hidden");
    if (elements.topbarLogoImg) {
      elements.topbarLogoImg.src = logoSrc;
      elements.topbarLogoImg.classList.remove("is-hidden");
    }
  } else {
    if (elements.brandLogoImg) {
      elements.brandLogoImg.removeAttribute("src");
      elements.brandLogoImg.classList.add("is-hidden");
    }
    elements.brandFallbackMark?.classList.remove("is-hidden");
    if (elements.topbarLogoImg) {
      elements.topbarLogoImg.removeAttribute("src");
      elements.topbarLogoImg.classList.add("is-hidden");
    }
  }
}

function updateNavSelection(sectionKey) {
  for (const btn of elements.navButtons) {
    if (btn.dataset.section === sectionKey) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  }
}

async function refreshDashboardCounts() {
  if (!state.session || state.activeSection !== "dashboard" || !canAccessWorkspace(state.session)) {
    return;
  }
  try {
    const [customersRes, productsRes, invoicesRes, businessRes, summaryRes] = await Promise.all([
      fetchCustomers({ is_active: true, page: 1, page_size: 1 }),
      fetchProducts({ is_active: true, page: 1, page_size: 1 }),
      fetchInvoices({ page: 1, page_size: 5 }),
      fetchBusinessProfile(),
      fetchSalesSummary({}),
    ]);
    state.session = { ...state.session, business: businessRes };
    state.counts = {
      customers: customersRes.total,
      products: productsRes.total,
      invoices: invoicesRes.total,
      recentInvoices: invoicesRes.items || [],
      summary: summaryRes,
    };
    if (state.activeSection === "dashboard") {
      renderActiveView();
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
    }
  }
}

function renderActiveView() {
  if (!state.session) {
    elements.appShell.classList.add("is-hidden");
    elements.authShell.classList.remove("is-hidden");
    elements.signOutBtn.classList.add("is-hidden");
    renderSaasAuthScreen(elements.authShell, {
      mode: state.authUi.mode,
      loading: state.authUi.loading,
      error: state.authUi.error,
      supportInfo: state.supportInfo,
      themeMode: getColorTheme(),
      onToggleTheme: toggleColorTheme,
      onModeChange: (mode) => {
        state.authUi.mode = mode;
        state.authUi.error = null;
        renderActiveView();
      },
      onLogin: handleLogin,
      onRegister: handleRegister,
    });
    return;
  }

  if (!canAccessWorkspace(state.session)) {
    elements.appShell.classList.add("is-hidden");
    elements.authShell.classList.remove("is-hidden");
    elements.signOutBtn.classList.add("is-hidden");
    renderAccountGateScreen(elements.authShell, {
      session: state.session,
      supportInfo: state.supportInfo,
      themeMode: getColorTheme(),
      onToggleTheme: toggleColorTheme,
      onRefreshStatus: async () => {
        try {
          state.session = await fetchCurrentSession();
          renderActiveView();
          if (canAccessWorkspace(state.session)) {
            showToast("Workspace unlocked! Welcome back.", "success");
            void refreshDashboardCounts();
          } else {
            showToast("Status refreshed. Still awaiting approval/activation.", "info");
          }
        } catch (err) {
          if (err instanceof ApiError && err.status === 401) {
            handleAuthExpired();
          }
        }
      },
      onActivated: async () => {
        state.session = await fetchCurrentSession();
        state.activeSection = "dashboard";
        renderActiveView();
        void refreshDashboardCounts();
      },
      onLogout: handleLogout,
    });
    return;
  }

  elements.authShell.classList.add("is-hidden");
  elements.appShell.classList.remove("is-hidden");
  elements.signOutBtn.classList.remove("is-hidden");
  elements.sidebarBusinessName.textContent = state.session.business?.name || "Business Workspace";
  elements.sidebarUserEmail.textContent = state.session.user?.email || "";
  elements.topbarTitle.textContent = getSectionTitle(state.activeSection);
  updateHeaderBusinessBranding(state.session.business);
  updateNavSelection(state.activeSection);
  syncSidebarUi();
  syncThemeToggleUi();

  if (state.activeSection === "customers") {
    void customersController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "products") {
    void productsController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "inventory") {
    void inventoryController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "invoices") {
    void invoicesController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "payments") {
    void paymentsController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "reports") {
    void reportsController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "notifications") {
    void notificationsController.mount(elements.mainContent);
    return;
  }
  if (state.activeSection === "subscription") {
    void subscriptionController.mountSubscription(elements.mainContent);
    return;
  }
  if (state.activeSection === "activation") {
    void subscriptionController.mountActivation(elements.mainContent);
    return;
  }

  renderSection(elements.mainContent, state.activeSection, {
    healthState: state.health,
    session: state.session,
    counts: state.counts,
    supportInfo: state.supportInfo,
    settingsState: state.settingsUi,
    themePresets: state.themePresets,
    onNavigate: navigateTo,
    onSaveBusiness: handleSaveBusiness,
    onUploadSignature: handleUploadSignature,
    onRemoveSignature: handleRemoveSignature,
    onUploadLogo: handleUploadLogo,
    onRemoveLogo: handleRemoveLogo,
    onSaveTheme: handleSaveTheme,
  });
}

async function navigateTo(sectionKey, { updateUrl = true } = {}) {
  setDrawerOpen(false);
  state.settingsUi.error = null;
  state.settingsUi.success = null;

  const targetHash = routeKeyToHash(sectionKey);
  if (updateUrl && window.location.hash !== targetHash) {
    window.location.hash = targetHash;
  }

  if (sectionKey === "invoices-new") {
    state.activeSection = "invoices";
    elements.topbarTitle.textContent = getSectionTitle("invoices");
    updateNavSelection("invoices");
    await invoicesController.openCreate(elements.mainContent);
    return;
  }

  if (typeof sectionKey === "string" && sectionKey.startsWith("invoice:")) {
    const invoiceId = Number.parseInt(sectionKey.split(":")[1], 10);
    state.activeSection = "invoices";
    elements.topbarTitle.textContent = getSectionTitle("invoices");
    updateNavSelection("invoices");
    await invoicesController.openDetail(elements.mainContent, invoiceId);
    return;
  }

  const safeSection = VALID_SECTIONS.has(sectionKey) ? sectionKey : "dashboard";
  state.activeSection = safeSection;

  if (safeSection === "settings" && state.session) {
    try {
      const [freshBusiness, appearance] = await Promise.all([
        fetchBusinessProfile(),
        fetchBusinessAppearance(),
      ]);
      state.session = { ...state.session, business: freshBusiness };
      state.themePresets = appearance?.presets || state.themePresets;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        handleAuthExpired();
        return;
      }
      state.settingsUi.error = err instanceof Error ? err.message : "Failed to load settings.";
    }
  } else if (safeSection === "dashboard" && state.session) {
    void refreshDashboardCounts();
  }

  renderActiveView();
}

async function handleLogin(payload) {
  state.authUi.loading = true;
  state.authUi.error = null;
  renderActiveView();

  try {
    state.session = await loginAccount(payload);
    state.activeSection = "dashboard";
    state.authUi.loading = false;
    void refreshDashboardCounts();
  } catch (err) {
    state.authUi.loading = false;
    state.authUi.error = err instanceof Error ? err.message : "Sign in failed.";
  }
  renderActiveView();
}

async function handleRegister(payload) {
  state.authUi.loading = true;
  state.authUi.error = null;
  renderActiveView();

  try {
    state.session = await registerAccount(payload);
    state.activeSection = "dashboard";
    state.authUi.loading = false;
    void refreshDashboardCounts();
  } catch (err) {
    state.authUi.loading = false;
    state.authUi.error = err instanceof Error ? err.message : "Account creation failed.";
  }
  renderActiveView();
}

async function handleLogout() {
  try {
    await logoutAccount();
  } finally {
    state.session = null;
    state.counts = {
      customers: null,
      products: null,
      invoices: null,
      recentInvoices: [],
      summary: null,
    };
    state.activeSection = "dashboard";
    state.authUi = { mode: "login", loading: false, error: null };
    state.settingsUi = {
      saving: false,
      uploadingSignature: false,
      uploadingLogo: false,
      savingTheme: false,
      error: null,
      success: null,
    };
    updateHeaderBusinessBranding(null);
    renderActiveView();
  }
}

async function handleSaveBusiness(payload) {
  state.settingsUi = {
    ...state.settingsUi,
    saving: true,
    error: null,
    success: null,
  };
  renderActiveView();

  try {
    const updated = await updateBusinessProfile(payload);
    state.session = { ...state.session, business: updated };
    state.settingsUi = {
      ...state.settingsUi,
      saving: false,
      error: null,
      success: "Business settings saved.",
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
      return;
    }
    state.settingsUi = {
      ...state.settingsUi,
      saving: false,
      uploadingSignature: false,
      error: err instanceof Error ? err.message : "Failed to save business settings.",
      success: null,
    };
  }
  renderActiveView();
}

async function handleUploadSignature(file) {
  if (!file) {
    state.settingsUi = {
      ...state.settingsUi,
      error: "Please choose a PNG, JPG/JPEG, or WebP signature image first.",
      success: null,
    };
    renderActiveView();
    return;
  }

  state.settingsUi = {
    ...state.settingsUi,
    uploadingSignature: true,
    error: null,
    success: null,
  };
  renderActiveView();

  try {
    const updated = await uploadBusinessSignature(file);
    state.session = { ...state.session, business: updated };
    state.settingsUi = {
      saving: false,
      uploadingSignature: false,
      error: null,
      success: "Signature uploaded and enabled on invoices.",
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
      return;
    }
    state.settingsUi = {
      saving: false,
      uploadingSignature: false,
      error: err instanceof Error ? err.message : "Failed to upload signature.",
      success: null,
    };
  }
  renderActiveView();
}

async function handleRemoveSignature() {
  state.settingsUi = {
    ...state.settingsUi,
    uploadingSignature: true,
    error: null,
    success: null,
  };
  renderActiveView();

  try {
    const updated = await removeBusinessSignature();
    state.session = { ...state.session, business: updated };
    state.settingsUi = {
      ...state.settingsUi,
      saving: false,
      uploadingSignature: false,
      error: null,
      success: "Signature removed.",
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
      return;
    }
    state.settingsUi = {
      ...state.settingsUi,
      saving: false,
      uploadingSignature: false,
      error: err instanceof Error ? err.message : "Failed to remove signature.",
      success: null,
    };
  }
  renderActiveView();
}

async function handleUploadLogo(file, isReplace = false) {
  if (!file) {
    state.settingsUi = {
      ...state.settingsUi,
      error: "Please choose a PNG, JPG/JPEG, or WebP logo image first.",
      success: null,
    };
    renderActiveView();
    return;
  }

  state.settingsUi = {
    ...state.settingsUi,
    uploadingLogo: true,
    error: null,
    success: null,
  };
  renderActiveView();

  try {
    const updated = await uploadBusinessLogo(file, isReplace);
    state.session = { ...state.session, business: updated };
    state.settingsUi = {
      ...state.settingsUi,
      uploadingLogo: false,
      error: null,
      success: isReplace ? "Business logo replaced." : "Business logo uploaded.",
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
      return;
    }
    state.settingsUi = {
      ...state.settingsUi,
      uploadingLogo: false,
      error: err instanceof Error ? err.message : "Failed to upload business logo.",
      success: null,
    };
  }
  renderActiveView();
}

async function handleRemoveLogo() {
  state.settingsUi = {
    ...state.settingsUi,
    uploadingLogo: true,
    error: null,
    success: null,
  };
  renderActiveView();

  try {
    const updated = await removeBusinessLogo();
    state.session = { ...state.session, business: updated };
    state.settingsUi = {
      ...state.settingsUi,
      uploadingLogo: false,
      error: null,
      success: "Business logo removed.",
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
      return;
    }
    state.settingsUi = {
      ...state.settingsUi,
      uploadingLogo: false,
      error: err instanceof Error ? err.message : "Failed to remove business logo.",
      success: null,
    };
  }
  renderActiveView();
}

async function handleSaveTheme(themePayload) {
  state.settingsUi = {
    ...state.settingsUi,
    savingTheme: true,
    error: null,
    success: null,
  };
  renderActiveView();

  try {
    const response = await updateInvoiceTheme(themePayload);
    const t = response?.theme || themePayload;
    state.themePresets = response?.presets || state.themePresets;
    if (state.session?.business) {
      state.session = {
        ...state.session,
        business: {
          ...state.session.business,
          invoice_theme_preset: t.preset,
          theme_primary_color: t.primary_color,
          theme_secondary_color: t.secondary_color,
          theme_accent_color: t.accent_color,
          theme_header_color: t.header_color,
          theme_table_header_color: t.table_header_color,
          theme_text_color: t.text_color,
          theme_border_color: t.border_color,
        },
      };
    }
    state.settingsUi = {
      ...state.settingsUi,
      savingTheme: false,
      error: null,
      success: "Invoice theme settings saved.",
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      handleAuthExpired();
      return;
    }
    state.settingsUi = {
      ...state.settingsUi,
      savingTheme: false,
      error: err instanceof Error ? err.message : "Failed to save invoice theme.",
      success: null,
    };
  }
  renderActiveView();
}

async function refreshHealth() {
  state.health = { loading: true, result: null, error: null };
  elements.healthRefreshBtn.dataset.state = "loading";
  elements.healthPillText.textContent = "Checking system...";

  if (state.session && state.activeSection === "dashboard") {
    renderActiveView();
  }

  try {
    const result = await fetchSystemHealth();
    state.health = { loading: false, result, error: null };
    renderHealthPill(elements.healthRefreshBtn, elements.healthPillText, result, null);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Failed to reach backend API.";
    state.health = { loading: false, result: null, error: message };
    renderHealthPill(elements.healthRefreshBtn, elements.healthPillText, null, message);
  }

  if (state.session && state.activeSection === "dashboard") {
    renderActiveView();
  }
}

function bindEvents() {
  if (eventsBound) return;
  eventsBound = true;

  elements.menuToggleBtn.addEventListener("click", () => toggleSidebar());
  elements.sidebarCloseBtn.addEventListener("click", () => {
    setDrawerOpen(false);
    elements.menuToggleBtn.focus();
  });
  elements.backdrop.addEventListener("click", () => {
    setDrawerOpen(false);
    elements.menuToggleBtn.focus();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebarState.mobileOpen) {
      setDrawerOpen(false);
      elements.menuToggleBtn.focus();
    }
  });

  const handleViewportChange = () => {
    if (!isMobileViewport() && sidebarState.mobileOpen) {
      sidebarState.mobileOpen = false;
    }
    syncSidebarUi();
  };
  if (typeof mobileMediaQuery.addEventListener === "function") {
    mobileMediaQuery.addEventListener("change", handleViewportChange);
  }
  window.addEventListener("resize", handleViewportChange);

  for (const imgEl of [elements.brandLogoImg, elements.topbarLogoImg]) {
    if (!imgEl) continue;
    imgEl.addEventListener("error", () => {
      imgEl.classList.add("is-hidden");
      if (imgEl === elements.brandLogoImg) {
        elements.brandFallbackMark?.classList.remove("is-hidden");
      }
    });
  }

  for (const btn of elements.navButtons) {
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      const section = btn.dataset.section || "dashboard";
      void navigateTo(section);
    });
  }

  window.addEventListener("hashchange", () => {
    if (!state.session) return;
    const nextRoute = parseRouteFromLocation();
    if (nextRoute !== state.activeSection) {
      void navigateTo(nextRoute, { updateUrl: false });
    }
  });

  elements.themeModeToggle?.addEventListener("click", () => {
    toggleColorTheme();
    showToast(
      getColorTheme() === "dark" ? "Dark mode enabled." : "Bright mode enabled.",
      "info",
      2400
    );
  });

  elements.newInvoiceBtn.addEventListener("click", () => {
    void navigateTo("invoices-new");
  });

  elements.signOutBtn.addEventListener("click", () => {
    void handleLogout();
  });

  elements.healthRefreshBtn.addEventListener("click", () => {
    void refreshHealth();
  });
}

async function init() {
  syncThemeToggleUi();
  bindEvents();
  void refreshHealth();

  try {
    state.supportInfo = await fetchSaasSupport();
  } catch {
    state.supportInfo = null;
  }

  const initialRoute = parseRouteFromLocation();

  try {
    state.session = await fetchCurrentSession();
    void refreshDashboardCounts();
  } catch {
    state.session = null;
  }

  if (state.session && canAccessWorkspace(state.session) && initialRoute !== "dashboard") {
    await navigateTo(initialRoute, { updateUrl: false });
    return;
  }

  renderActiveView();
}

void init();
