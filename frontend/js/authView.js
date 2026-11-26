/**
 * Liquid Glass SaaS Login, Registration, Forgot Password, and Account Gate UI.
 */

import { activateSubscriptionCode, forgotPasswordRequest } from "/js/api.js";
import { createCheckboxField, createElement, createField, showToast } from "/js/dom.js";
import { openModal } from "/js/modal.js";

function createPasswordField({ id, name, label, required = true, autocomplete = "current-password", help = "" }) {
  const wrapper = createElement("div", "form-field");
  const labelEl = createElement("label", "form-label", label);
  labelEl.setAttribute("for", id);

  const row = createElement("div", "password-input-wrap");
  const input = createElement("input", "form-input");
  input.id = id;
  input.name = name;
  input.type = "password";
  input.required = required;
  input.maxLength = 128;
  input.autocomplete = autocomplete;
  input.placeholder = "Enter password";

  const toggleBtn = createElement("button", "btn btn-sm password-toggle-btn", "Show");
  toggleBtn.type = "button";
  toggleBtn.setAttribute("aria-label", `Show ${label}`);
  toggleBtn.addEventListener("click", () => {
    const reveal = input.type === "password";
    input.type = reveal ? "text" : "password";
    toggleBtn.textContent = reveal ? "Hide" : "Show";
  });

  row.appendChild(input);
  row.appendChild(toggleBtn);
  wrapper.appendChild(labelEl);
  wrapper.appendChild(row);
  if (help) {
    wrapper.appendChild(createElement("span", "form-help", help));
  }
  return { wrapper, input };
}

function openForgotPasswordModal(prefillEmail = "") {
  openModal({
    title: "Reset Account Password",
    small: true,
    renderBody: (body, close) => {
      const info = createElement(
        "p",
        "section-subtitle",
        "Submit your registered email address to notify the RMSTORVIX administrator for a secure password reset."
      );
      const alertBox = createElement("div", "alert is-hidden");
      const form = createElement("form", "form-stack");
      const emailField = createField({
        id: "forgot-email",
        name: "email",
        label: "Registered Email *",
        type: "email",
        required: true,
        value: prefillEmail,
        placeholder: "owner@business.com",
      });
      const reasonField = createField({
        id: "forgot-reason",
        name: "reason",
        label: "Note for Administrator (Optional)",
        maxLength: 300,
        placeholder: "e.g. Locked out of workspace",
      });

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Close");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);
      const submitBtn = createElement("button", "btn btn-primary", "Send Reset Request");
      submitBtn.type = "submit";
      actions.appendChild(cancelBtn);
      actions.appendChild(submitBtn);

      form.appendChild(emailField.wrapper);
      form.appendChild(reasonField.wrapper);
      form.appendChild(actions);

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        submitBtn.disabled = true;
        submitBtn.textContent = "Sending...";
        try {
          const res = await forgotPasswordRequest({
            email: emailField.input.value.trim(),
            reason: reasonField.input.value.trim() || null,
          });
          alertBox.className = "alert alert-success";
          alertBox.textContent = res.message;
          submitBtn.textContent = "Request Sent";
        } catch (err) {
          alertBox.className = "alert alert-error";
          alertBox.textContent = err instanceof Error ? err.message : "Failed to submit request.";
          submitBtn.disabled = false;
          submitBtn.textContent = "Send Reset Request";
        }
      });

      body.appendChild(info);
      body.appendChild(alertBox);
      body.appendChild(form);
    },
  });
}

function buildAmbientBillingShowcase() {
  const showcase = createElement("div", "saas-auth-showcase");
  showcase.setAttribute("aria-hidden", "true");

  const glow1 = createElement("div", "saas-glow saas-glow-1");
  const glow2 = createElement("div", "saas-glow saas-glow-2");
  showcase.appendChild(glow1);
  showcase.appendChild(glow2);

  const heroCopy = createElement("div", "saas-showcase-copy");
  const pill = createElement("span", "saas-brand-pill", "RMSTORVIX • Cloud Billing & GST Suite");
  const h1 = createElement("h2", "saas-showcase-title", "Smart Invoicing, GST Compliance & Stock Control");
  const desc = createElement(
    "p",
    "saas-showcase-desc",
    "Manage tax-compliant CGST/SGST/IGST billing, UPI payment QR invoices, inventory tracking, custom PDF themes, and multi-tenant subscription governance."
  );
  heroCopy.appendChild(pill);
  heroCopy.appendChild(h1);
  heroCopy.appendChild(desc);

  // Subtle floating glassmorphic UI preview cards
  const cardsGrid = createElement("div", "saas-floating-grid");

  const invCard = createElement("div", "saas-float-card");
  invCard.appendChild(createElement("span", "saas-float-tag", "GST Invoice #RMX-1042"));
  invCard.appendChild(createElement("strong", "saas-float-metric", "INR 48,970.00"));
  invCard.appendChild(createElement("span", "saas-float-meta", "CGST 9% + SGST 9% • UPI QR Ready"));

  const salesCard = createElement("div", "saas-float-card saas-float-card-delayed");
  salesCard.appendChild(createElement("span", "saas-float-tag", "Collection Rate"));
  salesCard.appendChild(createElement("strong", "saas-float-metric", "96.4% Paid"));
  const miniBars = createElement("div", "saas-mini-bars");
  for (const pct of [42, 68, 56, 84, 72, 95]) {
    const bar = createElement("span", "saas-mini-bar");
    bar.style.height = `${pct}%`;
    miniBars.appendChild(bar);
  }
  salesCard.appendChild(miniBars);

  const invStockCard = createElement("div", "saas-float-card");
  invStockCard.appendChild(createElement("span", "saas-float-tag", "HSN & Inventory"));
  invStockCard.appendChild(createElement("strong", "saas-float-metric", "Auto GST + HSN 998314"));
  invStockCard.appendChild(createElement("span", "saas-float-meta", "Real-time Stock & PDF Signatures"));

  cardsGrid.appendChild(invCard);
  cardsGrid.appendChild(salesCard);
  cardsGrid.appendChild(invStockCard);

  showcase.appendChild(heroCopy);
  showcase.appendChild(cardsGrid);
  return showcase;
}

export function renderSaasAuthScreen(
  container,
  {
    mode,
    loading,
    error,
    supportInfo,
    themeMode = "light",
    onToggleTheme,
    onModeChange,
    onLogin,
    onRegister,
  }
) {
  container.replaceChildren();
  const stage = createElement("div", "saas-auth-stage");
  stage.appendChild(buildAmbientBillingShowcase());

  const card = createElement("section", "auth-card auth-card-glass");
  if (mode === "register") {
    card.classList.add("auth-card-wide");
  }

  const header = createElement("div", "auth-header");
  const topRow = createElement("div", "auth-top-row");
  const brandRow = createElement("div", "brand");
  const mark = createElement("span", "brand-mark", "RX");
  mark.setAttribute("aria-hidden", "true");
  brandRow.appendChild(mark);
  const brandTextWrap = createElement("div", "auth-brand-text");
  brandTextWrap.appendChild(createElement("span", "auth-brand-name", "RMSTORVIX"));
  brandTextWrap.appendChild(createElement("span", "auth-brand-sub", "Invoice & Billing System"));
  brandRow.appendChild(brandTextWrap);
  topRow.appendChild(brandRow);

  if (typeof onToggleTheme === "function") {
    const modeBtn = createElement(
      "button",
      "btn btn-sm",
      themeMode === "dark" ? "Bright Mode" : "Dark Mode"
    );
    modeBtn.type = "button";
    modeBtn.id = "auth-theme-toggle";
    modeBtn.addEventListener("click", onToggleTheme);
    topRow.appendChild(modeBtn);
  }
  header.appendChild(topRow);
  header.appendChild(
    createElement("h1", "auth-title", mode === "register" ? "Register Business Workspace" : "Welcome Back")
  );
  header.appendChild(
    createElement(
      "p",
      "auth-subtitle",
      mode === "register"
        ? "Create your business profile. Accounts enter Pending Approval until reviewed and activated by an administrator."
        : "Sign in to access your RMSTORVIX invoicing workspace."
    )
  );
  card.appendChild(header);

  const tabs = createElement("div", "auth-tabs");
  tabs.setAttribute("role", "tablist");
  const loginTab = createElement("button", "auth-tab-btn", "Sign In");
  loginTab.type = "button";
  loginTab.setAttribute("role", "tab");
  loginTab.setAttribute("aria-selected", String(mode === "login"));
  loginTab.addEventListener("click", () => onModeChange("login"));

  const registerTab = createElement("button", "auth-tab-btn", "Create Account");
  registerTab.type = "button";
  registerTab.setAttribute("role", "tab");
  registerTab.setAttribute("aria-selected", String(mode === "register"));
  registerTab.addEventListener("click", () => onModeChange("register"));

  tabs.appendChild(loginTab);
  tabs.appendChild(registerTab);
  card.appendChild(tabs);

  if (error) {
    const alert = createElement("div", "alert alert-error", error);
    alert.setAttribute("role", "alert");
    card.appendChild(alert);
  }

  const clientErrorSlot = createElement("div", "alert alert-error is-hidden");
  clientErrorSlot.setAttribute("role", "alert");
  card.appendChild(clientErrorSlot);

  const form = createElement("form", "form-stack");

  if (mode === "register") {
    const grid = createElement("div", "form-grid");
    const ownerField = createField({
      id: "auth-full-name",
      name: "full_name",
      label: "Owner Full Name *",
      required: true,
      maxLength: 160,
      autocomplete: "name",
      placeholder: "Rajiv Maurya",
    });
    const bizField = createField({
      id: "auth-business-name",
      name: "business_name",
      label: "Business / Shop Name *",
      required: true,
      maxLength: 160,
      autocomplete: "organization",
      placeholder: "RR Enterprises Pvt Ltd",
    });
    const mobileField = createField({
      id: "auth-phone",
      name: "phone",
      label: "Mobile Number *",
      type: "tel",
      required: true,
      maxLength: 40,
      autocomplete: "tel",
      placeholder: "+91 9876543210",
    });
    const emailField = createField({
      id: "auth-email",
      name: "email",
      label: "Business Email *",
      type: "email",
      required: true,
      maxLength: 254,
      autocomplete: "email",
      placeholder: "owner@business.com",
    });
    const gstinField = createField({
      id: "auth-gstin",
      name: "gstin",
      label: "GSTIN (Optional)",
      maxLength: 64,
      placeholder: "27AABCU9603R1ZM",
    });

    const typeWrap = createElement("div", "form-field");
    const typeLbl = createElement("label", "form-label", "Business Type *");
    typeLbl.setAttribute("for", "auth-business-type");
    const typeSelect = createElement("select", "form-input");
    typeSelect.id = "auth-business-type";
    for (const optLabel of [
      "Retail & Store",
      "Wholesale & Distribution",
      "Services & Consulting",
      "Manufacturing",
      "IT & SaaS",
      "Freelancer / Sole Proprietor",
      "Other",
    ]) {
      const opt = createElement("option", "", optLabel);
      opt.value = optLabel;
      typeSelect.appendChild(opt);
    }
    typeWrap.appendChild(typeLbl);
    typeWrap.appendChild(typeSelect);

    const addressField = createField({
      id: "auth-address",
      name: "address",
      label: "Business Address *",
      required: true,
      maxLength: 200,
      fullWidth: true,
      autocomplete: "street-address",
      placeholder: "Shop / Street, City, State",
    });

    const passField = createPasswordField({
      id: "auth-password",
      name: "password",
      label: "Password *",
      autocomplete: "new-password",
      help: "Minimum 8 characters.",
    });
    const confirmField = createPasswordField({
      id: "auth-confirm-password",
      name: "confirm_password",
      label: "Confirm Password *",
      autocomplete: "new-password",
    });

    for (const w of [
      ownerField.wrapper,
      bizField.wrapper,
      mobileField.wrapper,
      emailField.wrapper,
      gstinField.wrapper,
      typeWrap,
      addressField.wrapper,
      passField.wrapper,
      confirmField.wrapper,
    ]) {
      grid.appendChild(w);
    }
    form.appendChild(grid);

    const termsCheck = createCheckboxField({
      id: "auth-terms",
      name: "terms_accepted",
      label: "I accept the RMSTORVIX SaaS Terms of Service and Privacy Policy.",
      checked: false,
      fullWidth: true,
    });
    form.appendChild(termsCheck.wrapper);

    const submitBtn = createElement(
      "button",
      "btn btn-primary",
      loading ? "Submitting Registration..." : "Register Account"
    );
    submitBtn.type = "submit";
    submitBtn.disabled = Boolean(loading);
    form.appendChild(submitBtn);

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      clientErrorSlot.classList.add("is-hidden");
      const pwd = passField.input.value;
      const conf = confirmField.input.value;
      if (pwd !== conf) {
        clientErrorSlot.textContent = "Password and Confirm Password do not match.";
        clientErrorSlot.classList.remove("is-hidden");
        return;
      }
      if (!termsCheck.input.checked) {
        clientErrorSlot.textContent = "Please accept the Terms & Conditions before registering.";
        clientErrorSlot.classList.remove("is-hidden");
        return;
      }
      onRegister({
        full_name: ownerField.input.value.trim(),
        business_name: bizField.input.value.trim(),
        phone: mobileField.input.value.trim(),
        email: emailField.input.value.trim(),
        gstin: gstinField.input.value.trim().toUpperCase() || null,
        business_type: typeSelect.value,
        address: addressField.input.value.trim(),
        password: pwd,
        confirm_password: conf,
        terms_accepted: true,
      });
    });
  } else {
    const emailField = createField({
      id: "auth-email",
      name: "email",
      label: "Email Address",
      type: "email",
      required: true,
      maxLength: 254,
      autocomplete: "email",
      placeholder: "owner@business.com",
    });
    const passField = createPasswordField({
      id: "auth-password",
      name: "password",
      label: "Password",
      autocomplete: "current-password",
    });

    const extrasRow = createElement("div", "auth-extras-row");
    const rememberCheck = createCheckboxField({
      id: "auth-remember",
      name: "remember_me",
      label: "Remember me (30 days)",
      checked: false,
    });
    const forgotBtn = createElement("button", "auth-link-btn", "Forgot password?");
    forgotBtn.type = "button";
    forgotBtn.addEventListener("click", () =>
      openForgotPasswordModal(emailField.input.value.trim())
    );
    extrasRow.appendChild(rememberCheck.wrapper);
    extrasRow.appendChild(forgotBtn);

    form.appendChild(emailField.wrapper);
    form.appendChild(passField.wrapper);
    form.appendChild(extrasRow);

    const submitBtn = createElement(
      "button",
      "btn btn-primary",
      loading ? "Signing In..." : "Sign In"
    );
    submitBtn.type = "submit";
    submitBtn.disabled = Boolean(loading);
    form.appendChild(submitBtn);

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      onLogin({
        email: emailField.input.value.trim(),
        password: passField.input.value,
        remember_me: Boolean(rememberCheck.input.checked),
      });
    });
  }

  card.appendChild(form);

  const footer = createElement("div", "auth-support-footer");
  const switchRow = createElement("div", "auth-switch-row");
  const switchBtn = createElement(
    "button",
    "auth-link-btn",
    mode === "register"
      ? "Already registered? Sign In"
      : "New to RMSTORVIX? Register Business Account"
  );
  switchBtn.type = "button";
  switchBtn.addEventListener("click", () => onModeChange(mode === "register" ? "login" : "register"));
  switchRow.appendChild(switchBtn);

  const adminLink = createElement("a", "auth-link-btn", "Admin Console");
  adminLink.href = "/admin";
  switchRow.appendChild(adminLink);
  footer.appendChild(switchRow);

  const supEmail = supportInfo?.support_email || "support@rmstorvix.com";
  const supPhone = supportInfo?.support_phone || "+91-1800-000-0000";
  footer.appendChild(
    createElement("p", "auth-support-text", `Support: ${supEmail} • ${supPhone}`)
  );
  card.appendChild(footer);

  stage.appendChild(card);
  container.appendChild(stage);
}

export function renderAccountGateScreen(
  container,
  { session, supportInfo, onRefreshStatus, onActivated, onLogout, onToggleTheme, themeMode }
) {
  container.replaceChildren();
  const stage = createElement("div", "saas-auth-stage");
  stage.appendChild(buildAmbientBillingShowcase());

  const user = session.user;
  const biz = session.business;
  const sub = session.subscription;
  const approval = user?.approval_status || "PENDING_APPROVAL";
  const subStatus = sub?.status || biz?.subscription_status || "NOT_ACTIVATED";

  const card = createElement("section", "auth-card auth-card-glass auth-card-wide");
  const topRow = createElement("div", "auth-top-row");
  const brandRow = createElement("div", "brand");
  brandRow.appendChild(createElement("span", "brand-mark", "RX"));
  brandRow.appendChild(createElement("span", "auth-brand-name", "RMSTORVIX"));
  topRow.appendChild(brandRow);

  const actionGroup = createElement("div", "topbar-actions");
  if (typeof onToggleTheme === "function") {
    const modeBtn = createElement(
      "button",
      "btn btn-sm",
      themeMode === "dark" ? "Bright Mode" : "Dark Mode"
    );
    modeBtn.type = "button";
    modeBtn.addEventListener("click", onToggleTheme);
    actionGroup.appendChild(modeBtn);
  }
  const logoutBtn = createElement("button", "btn btn-sm", "Sign Out");
  logoutBtn.type = "button";
  logoutBtn.addEventListener("click", onLogout);
  actionGroup.appendChild(logoutBtn);
  topRow.appendChild(actionGroup);
  card.appendChild(topRow);

  const isPending = approval === "PENDING_APPROVAL";
  const title = isPending
    ? "Registration Submitted — Pending Administrator Approval"
    : approval === "APPROVED" && subStatus === "NOT_ACTIVATED"
    ? "Account Approved — Activate Your Subscription"
    : `Account Status: ${approval} (${subStatus})`;

  card.appendChild(createElement("h1", "auth-title", title));

  const statusPillRow = createElement("div", "gate-badge-row");
  statusPillRow.appendChild(createElement("span", "badge badge-partially_paid", `Account: ${approval}`));
  statusPillRow.appendChild(createElement("span", "badge badge-draft", `Subscription: ${subStatus}`));
  card.appendChild(statusPillRow);

  const summaryMsg = isPending
    ? `Thank you for registering "${biz?.name || "your business"}". Your account status is PENDING_APPROVAL and your subscription status is NOT_ACTIVATED. Please contact the administrator to approve your business account and activate a subscription plan.`
    : approval === "APPROVED" && subStatus === "NOT_ACTIVATED"
    ? `Great news! Your account for "${biz?.name || "your business"}" has been approved by the administrator. Enter your activation code below or contact the administrator to start your subscription.`
    : `Your workspace is currently restricted (${approval} / ${subStatus}). Contact the administrator for assistance.`;

  const banner = createElement("div", "banner", summaryMsg);
  card.appendChild(banner);

  const infoGrid = createElement("div", "health-details");
  for (const [k, v] of [
    ["Owner", user?.full_name || "—"],
    ["Email", user?.email || "—"],
    ["Business", biz?.name || "—"],
    ["Support Email", supportInfo?.support_email || "support@rmstorvix.com"],
    ["Support Phone", supportInfo?.support_phone || "+91-1800-000-0000"],
  ]) {
    const row = createElement("div", "health-row");
    row.appendChild(createElement("span", "health-key", k));
    row.appendChild(createElement("span", "health-val", v));
    infoGrid.appendChild(row);
  }
  card.appendChild(infoGrid);

  // Only approved users with self-activation enabled can submit an activation code cleanly (never pending!)
  if (approval === "APPROVED" && sub?.can_self_activate) {
    const actBox = createElement("form", "form-stack");
    const errSlot = createElement("div", "alert alert-error is-hidden");
    const codeField = createField({
      id: "gate-activation-code",
      name: "code",
      label: "Enter Subscription Activation Code",
      required: true,
      maxLength: 32,
      placeholder: "RMX-XXXX-XXXX-XXXX",
    });
    const actBtn = createElement("button", "btn btn-primary", "Activate Subscription");
    actBtn.type = "submit";
    actBox.appendChild(errSlot);
    actBox.appendChild(codeField.wrapper);
    actBox.appendChild(actBtn);
    actBox.addEventListener("submit", async (e) => {
      e.preventDefault();
      actBtn.disabled = true;
      actBtn.textContent = "Activating...";
      errSlot.classList.add("is-hidden");
      try {
        const updatedSub = await activateSubscriptionCode(codeField.input.value.trim().toUpperCase());
        showToast(`Subscription activated (${updatedSub.plan_name})!`, "success");
        await onActivated();
      } catch (err) {
        actBtn.disabled = false;
        actBtn.textContent = "Activate Subscription";
        errSlot.textContent = err instanceof Error ? err.message : "Activation failed.";
        errSlot.classList.remove("is-hidden");
      }
    });
    card.appendChild(actBox);
  }

  const actions = createElement("div", "form-actions");
  const refreshBtn = createElement("button", "btn btn-primary", "Refresh Approval Status");
  refreshBtn.type = "button";
  refreshBtn.addEventListener("click", onRefreshStatus);
  actions.appendChild(refreshBtn);
  card.appendChild(actions);

  stage.appendChild(card);
  container.appendChild(stage);
}
