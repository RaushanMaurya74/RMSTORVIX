/**
 * RMSTORVIX Separate Administrator Control Plane Bootstrapper (/admin).
 * Never hardcodes or embeds administrator passwords anywhere in client code.
 */

import {
  adminLogin,
  adminLogout,
  changeAdminPassword,
  fetchAdminMe,
} from "/js/adminApi.js";
import { createAdminViewsController } from "/js/adminViews.js";
import { createElement, createField, showToast } from "/js/dom.js";

const SECTION_TITLES = {
  overview: "Admin Dashboard",
  approvals: "Pending Approvals",
  users: "User & Business Management",
  subscriptions: "Subscription Management",
  codes: "Activation Codes",
  plans: "Plans & Quotas",
  notifications: "Admin Notifications",
  reports: "SaaS Analytics & Reports",
  audit: "Administrator Audit Logs",
  settings: "Global SaaS & Admin Settings",
};

const state = {
  admin: null,
  activeSection: "overview",
  loading: false,
  authError: null,
  mobileOpen: false,
  desktopCollapsed: false,
};

const els = {
  authShell: document.getElementById("admin-auth-shell"),
  appShell: document.getElementById("admin-app-shell"),
  sidebar: document.getElementById("admin-sidebar"),
  backdrop: document.getElementById("admin-sidebar-backdrop"),
  menuToggleBtn: document.getElementById("admin-menu-toggle-btn"),
  closeBtn: document.getElementById("admin-sidebar-close-btn"),
  navButtons: Array.from(document.querySelectorAll(".admin-nav-btn")),
  topbarTitle: document.getElementById("admin-topbar-title"),
  mainContent: document.getElementById("admin-main-content"),
  footerName: document.getElementById("admin-footer-name"),
  footerEmail: document.getElementById("admin-footer-email"),
  refreshBtn: document.getElementById("admin-refresh-btn"),
  signOutBtn: document.getElementById("admin-sign-out-btn"),
};

const views = createAdminViewsController({
  onAuthExpired: () => {
    state.admin = null;
    render();
  },
  onAdminUpdated: (admin) => {
    state.admin = admin;
    render();
  },
  onNavigate: (sec) => {
    navigateTo(sec);
  },
});

function syncSidebar() {
  const isMobile = window.innerWidth <= 768;
  if (isMobile) {
    els.appShell.classList.remove("sidebar-collapsed");
    els.sidebar.classList.toggle("is-open", state.mobileOpen);
    els.backdrop.classList.toggle("is-visible", state.mobileOpen);
  } else {
    els.sidebar.classList.remove("is-open");
    els.backdrop.classList.remove("is-visible");
    els.appShell.classList.toggle("sidebar-collapsed", state.desktopCollapsed);
  }
}

function renderAdminLogin() {
  els.authShell.replaceChildren();
  const card = createElement("section", "admin-glass-card");

  const brand = createElement("div", "brand");
  brand.appendChild(createElement("span", "brand-mark admin-brand-mark", "RX"));
  const bt = createElement("div", "auth-brand-text");
  bt.appendChild(createElement("span", "auth-brand-name", "RMSTORVIX ADMIN"));
  bt.appendChild(createElement("span", "auth-brand-sub", "SaaS Governance Control Plane"));
  brand.appendChild(bt);

  card.appendChild(brand);
  card.appendChild(createElement("h1", "auth-title", "Administrator Sign In"));
  card.appendChild(
    createElement(
      "p",
      "auth-subtitle",
      "Isolated administrator portal for business approvals, subscriptions, activation codes, and audit governance."
    )
  );

  if (state.authError) {
    card.appendChild(createElement("div", "alert alert-error", state.authError));
  }

  const form = createElement("form", "form-stack");
  const emailField = createField({
    id: "adm-login-email",
    name: "email",
    label: "Administrator Email",
    type: "email",
    required: true,
    placeholder: "Enter administrator email",
  });

  const pwdWrap = createElement("div", "form-field");
  const pwdLbl = createElement("label", "form-label", "Password");
  pwdLbl.setAttribute("for", "adm-login-pwd");
  const pwdRow = createElement("div", "password-input-wrap");
  const pwdInput = createElement("input", "form-input");
  pwdInput.id = "adm-login-pwd";
  pwdInput.type = "password";
  pwdInput.required = true;
  pwdInput.placeholder = "Enter administrator password";
  const toggleBtn = createElement("button", "btn btn-sm password-toggle-btn", "Show");
  toggleBtn.type = "button";
  toggleBtn.addEventListener("click", () => {
    const show = pwdInput.type === "password";
    pwdInput.type = show ? "text" : "password";
    toggleBtn.textContent = show ? "Hide" : "Show";
  });
  pwdRow.append(pwdInput, toggleBtn);
  pwdWrap.append(pwdLbl, pwdRow);

  const subBtn = createElement("button", "btn btn-primary", state.loading ? "Authenticating..." : "Sign In to Admin Panel");
  subBtn.type = "submit";
  subBtn.disabled = state.loading;

  form.append(emailField.wrapper, pwdWrap, subBtn);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    state.loading = true;
    state.authError = null;
    render();
    try {
      const res = await adminLogin({
        email: emailField.input.value.trim(),
        password: pwdInput.value,
      });
      state.admin = res.admin;
      state.loading = false;
      render();
    } catch (err) {
      state.loading = false;
      state.authError = err instanceof Error ? err.message : "Authentication failed.";
      render();
    }
  });

  const foot = createElement("div", "auth-support-footer");
  const backLink = createElement("a", "auth-link-btn", "← Return to Business Portal");
  backLink.href = "/";
  foot.appendChild(backLink);

  card.append(form, foot);
  els.authShell.appendChild(card);
}

function renderForcedPasswordChange() {
  els.authShell.replaceChildren();
  const card = createElement("section", "admin-glass-card");
  card.appendChild(createElement("h1", "auth-title", "Security Action Required: Change Initial Password"));
  card.appendChild(
    createElement(
      "p",
      "auth-subtitle",
      `Signed in as ${state.admin.email}. Update the seeded initial password before accessing administrator controls.`
    )
  );

  const errSlot = createElement("div", "alert alert-error is-hidden");
  const form = createElement("form", "form-stack");
  const curF = createField({ id: "fpc-cur", name: "current_password", label: "Current Password *", type: "password", required: true });
  const newF = createField({ id: "fpc-new", name: "new_password", label: "New Strong Password *", type: "password", required: true, help: "Minimum 10 characters." });
  const conF = createField({ id: "fpc-con", name: "confirm_password", label: "Confirm New Password *", type: "password", required: true });

  const actions = createElement("div", "form-actions");
  const logoutBtn = createElement("button", "btn", "Sign Out");
  logoutBtn.type = "button";
  logoutBtn.addEventListener("click", async () => {
    await adminLogout();
    state.admin = null;
    render();
  });
  const saveBtn = createElement("button", "btn btn-primary", "Update Password & Continue");
  saveBtn.type = "submit";
  actions.append(logoutBtn, saveBtn);

  form.append(errSlot, curF.wrapper, newF.wrapper, conF.wrapper, actions);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    saveBtn.disabled = true;
    errSlot.classList.add("is-hidden");
    try {
      const res = await changeAdminPassword({
        current_password: curF.input.value,
        new_password: newF.input.value,
        confirm_password: conF.input.value,
      });
      state.admin = res.admin;
      showToast("Administrator password updated.", "success");
      render();
    } catch (err) {
      saveBtn.disabled = false;
      errSlot.textContent = err instanceof Error ? err.message : "Password change failed.";
      errSlot.classList.remove("is-hidden");
    }
  });

  card.appendChild(form);
  els.authShell.appendChild(card);
}

function navigateTo(section) {
  state.activeSection = SECTION_TITLES[section] ? section : "overview";
  state.mobileOpen = false;
  window.location.hash = `#/${state.activeSection}`;
  render();
}

function render() {
  if (!state.admin) {
    els.appShell.classList.add("is-hidden");
    els.authShell.classList.remove("is-hidden");
    renderAdminLogin();
    return;
  }

  if (state.admin.must_change_password) {
    els.appShell.classList.add("is-hidden");
    els.authShell.classList.remove("is-hidden");
    renderForcedPasswordChange();
    return;
  }

  els.authShell.classList.add("is-hidden");
  els.appShell.classList.remove("is-hidden");
  els.footerName.textContent = state.admin.full_name;
  els.footerEmail.textContent = state.admin.email;
  els.topbarTitle.textContent = SECTION_TITLES[state.activeSection] || "Admin Dashboard";

  for (const btn of els.navButtons) {
    if (btn.dataset.section === state.activeSection) {
      btn.setAttribute("aria-current", "page");
    } else {
      btn.removeAttribute("aria-current");
    }
  }
  syncSidebar();
  void views.mount(state.activeSection, els.mainContent);
}

function bindEvents() {
  els.menuToggleBtn.addEventListener("click", () => {
    if (window.innerWidth <= 768) state.mobileOpen = !state.mobileOpen;
    else state.desktopCollapsed = !state.desktopCollapsed;
    syncSidebar();
  });
  els.closeBtn.addEventListener("click", () => {
    state.mobileOpen = false;
    syncSidebar();
  });
  els.backdrop.addEventListener("click", () => {
    state.mobileOpen = false;
    syncSidebar();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && state.mobileOpen) {
      state.mobileOpen = false;
      syncSidebar();
    }
  });
  for (const btn of els.navButtons) {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      navigateTo(btn.dataset.section || "overview");
    });
  }
  els.refreshBtn.addEventListener("click", () => render());
  els.signOutBtn.addEventListener("click", async () => {
    await adminLogout();
    state.admin = null;
    render();
  });
}

async function init() {
  bindEvents();
  const h = (window.location.hash || "").replace(/^#\/?/, "");
  if (SECTION_TITLES[h]) state.activeSection = h;
  try {
    const res = await fetchAdminMe();
    state.admin = res.admin;
  } catch {
    state.admin = null;
  }
  render();
}

void init();
