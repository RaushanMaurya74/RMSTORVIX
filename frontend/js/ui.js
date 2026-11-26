/**
 * Safe DOM rendering and application shell UI helpers.
 * Uses textContent instead of raw HTML interpolation for dynamic strings.
 */

import { changeUserPassword, getBusinessLogoUrl, getBusinessSignatureUrl } from "/js/api.js";
import { createCheckboxField, createElement, createField, formatCurrency, showToast } from "/js/dom.js";
import { openConfirmDialog } from "/js/modal.js";
import {
  DEFAULT_THEME,
  INVOICE_THEME_PRESETS,
  extractThemeFromBusiness,
  normalizeHex,
  renderSampleInvoicePreview,
} from "/js/themePreview.js";
import { buildSubscriptionSummaryCard } from "/js/subscriptionView.js";

const SECTION_META = {
  dashboard: {
    title: "Dashboard",
    subtitle: "Overview of your invoicing workspace and business readiness.",
    emptyTitle: "No invoices recorded yet",
    emptyText:
      "Customers and Products/Services are ready. Invoice creation with server-calculated totals will be added next.",
  },
  invoices: {
    title: "Invoices",
    subtitle: "Create, review, issue, and download PDF invoices.",
    emptyTitle: "Invoices module is queued for Phase 4",
    emptyText:
      "Invoices with server-calculated totals, line items, and PDF export will appear here in Phase 4.",
  },
  customers: {
    title: "Customers",
    subtitle: "Manage customer contacts and billing addresses.",
  },
  products: {
    title: "Products / Services",
    subtitle: "Configure reusable items, prices, and tax rules.",
  },
  inventory: {
    title: "Inventory / Stock",
    subtitle: "Monitor stock levels, identify low inventory, and adjust quantities.",
  },
  payments: {
    title: "Payments",
    subtitle: "Record invoice payments and monitor balances.",
    emptyTitle: "Payments module is queued for upcoming phases",
    emptyText:
      "Payment entry tracking and automatic invoice status updates will be added alongside the invoice lifecycle.",
  },
  reports: {
    title: "Reports",
    subtitle: "Review billing summaries, collections, and tax totals.",
    emptyTitle: "Reports module is queued for upcoming phases",
    emptyText:
      "Sales and invoice summary reports with date filters will appear here once invoices and payments are active.",
  },
  notifications: {
    title: "Notifications",
    subtitle: "Review overdue invoices, low-stock items, and recent billing events.",
  },
  subscription: {
    title: "Subscription & Plan",
    subtitle: "Track plan expiry countdown, remaining days/hours, and feature quota usage.",
  },
  activation: {
    title: "Activate Subscription",
    subtitle: "Redeem a unique activation code issued by the administrator.",
  },
  settings: {
    title: "Business Settings",
    subtitle: "Configure business identity, billing contact, currency, and invoice numbering.",
  },
};

export function getSectionTitle(sectionKey) {
  return (SECTION_META[sectionKey] || SECTION_META.dashboard).title;
}

export function renderHealthPill(pillEl, textEl, healthResult, errorMessage) {
  if (errorMessage) {
    pillEl.dataset.state = "error";
    textEl.textContent = "API Unreachable";
    return;
  }

  const data = healthResult?.data;
  if (!data) {
    pillEl.dataset.state = "loading";
    textEl.textContent = "Checking system...";
    return;
  }

  if (data.status === "ok") {
    pillEl.dataset.state = "ok";
    textEl.textContent = "API & DB Connected";
  } else {
    pillEl.dataset.state = "degraded";
    textEl.textContent = "API Up • DB Offline";
  }
}

export function renderAuthScreen(
  container,
  { mode, loading, error, themeMode = "light", onToggleTheme, onModeChange, onLogin, onRegister }
) {
  container.replaceChildren();
  const card = createElement("section", "auth-card");

  const header = createElement("div", "auth-header");
  const topRow = createElement("div", "auth-top-row");
  const brandRow = createElement("div", "brand");
  const mark = createElement("span", "brand-mark", "IB");
  mark.setAttribute("aria-hidden", "true");
  brandRow.appendChild(mark);
  brandRow.appendChild(createElement("span", "", "Invoice & Billing System"));
  topRow.appendChild(brandRow);

  if (typeof onToggleTheme === "function") {
    const modeBtn = createElement(
      "button",
      "btn btn-sm",
      themeMode === "dark" ? "Light Mode" : "Dark Mode"
    );
    modeBtn.type = "button";
    modeBtn.id = "auth-theme-toggle";
    modeBtn.setAttribute("aria-label", "Toggle dark and light mode");
    modeBtn.addEventListener("click", onToggleTheme);
    topRow.appendChild(modeBtn);
  }
  header.appendChild(topRow);
  header.appendChild(
    createElement("h1", "auth-title", mode === "register" ? "Create Business Account" : "Sign In")
  );
  header.appendChild(
    createElement(
      "p",
      "auth-subtitle",
      mode === "register"
        ? "Set up your login and initial business workspace."
        : "Sign in to manage your business, customers, products, and invoices."
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

  const form = createElement("form", "form-stack");

  let fullNameInput = null;
  let businessNameInput = null;
  if (mode === "register") {
    const fullNameField = createField({
      id: "auth-full-name",
      name: "full_name",
      label: "Full Name",
      required: true,
      maxLength: 160,
      autocomplete: "name",
      placeholder: "Alex Morgan",
    });
    const businessField = createField({
      id: "auth-business-name",
      name: "business_name",
      label: "Business Name",
      required: true,
      maxLength: 160,
      autocomplete: "organization",
      placeholder: "Northwind Studio LLC",
    });
    fullNameInput = fullNameField.input;
    businessNameInput = businessField.input;
    form.appendChild(fullNameField.wrapper);
    form.appendChild(businessField.wrapper);
  }

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
  const passwordField = createField({
    id: "auth-password",
    name: "password",
    label: "Password",
    type: "password",
    required: true,
    maxLength: 128,
    autocomplete: mode === "register" ? "new-password" : "current-password",
    help: mode === "register" ? "Minimum 8 characters." : "",
  });

  form.appendChild(emailField.wrapper);
  form.appendChild(passwordField.wrapper);

  const submitBtn = createElement(
    "button",
    "btn btn-primary",
    loading
      ? mode === "register"
        ? "Creating Account..."
        : "Signing In..."
      : mode === "register"
      ? "Create Account"
      : "Sign In"
  );
  submitBtn.type = "submit";
  submitBtn.disabled = Boolean(loading);
  form.appendChild(submitBtn);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (mode === "register") {
      onRegister({
        full_name: fullNameInput.value.trim(),
        business_name: businessNameInput.value.trim(),
        email: emailField.input.value.trim(),
        password: passwordField.input.value,
      });
    } else {
      onLogin({
        email: emailField.input.value.trim(),
        password: passwordField.input.value,
      });
    }
  });

  card.appendChild(form);
  container.appendChild(card);
}

function buildHealthCard(healthState) {
  const card = createElement("section", "card");
  card.setAttribute("aria-label", "System health status");

  const header = createElement("div", "card-header");
  header.appendChild(createElement("h2", "card-title", "System Readiness"));
  card.appendChild(header);

  if (healthState.loading) {
    card.appendChild(createElement("p", "section-subtitle", "Checking FastAPI and PostgreSQL connectivity..."));
    return card;
  }

  if (healthState.error) {
    card.appendChild(createElement("div", "banner", healthState.error));
    return card;
  }

  const data = healthState.result?.data;
  if (!data) {
    card.appendChild(createElement("p", "section-subtitle", "No health diagnostics available."));
    return card;
  }

  const details = createElement("div", "health-details");
  const rows = [
    ["Service", data.service || "Unknown"],
    ["Environment", data.environment || "Unknown"],
    ["API Status", data.status === "ok" ? "Healthy" : "Degraded"],
    ["Database", data.database?.status === "connected" ? "Connected" : "Disconnected"],
    ["Target", data.database?.target || "Not configured"],
    [
      "Latency",
      typeof data.database?.latency_ms === "number" ? `${data.database.latency_ms} ms` : "—",
    ],
  ];

  for (const [key, val] of rows) {
    const row = createElement("div", "health-row");
    row.appendChild(createElement("span", "health-key", key));
    row.appendChild(createElement("span", "health-val", String(val)));
    details.appendChild(row);
  }

  card.appendChild(details);
  return card;
}

function renderBusinessSettingsSection(
  container,
  {
    business,
    settingsState,
    themePresets,
    onSaveBusiness,
    onUploadSignature,
    onRemoveSignature,
    onUploadLogo,
    onRemoveLogo,
    onSaveTheme,
  }
) {
  if (settingsState.error) {
    const alert = createElement("div", "alert alert-error", settingsState.error);
    alert.setAttribute("role", "alert");
    container.appendChild(alert);
  }
  if (settingsState.success) {
    const alert = createElement("div", "alert alert-success", settingsState.success);
    alert.setAttribute("role", "status");
    container.appendChild(alert);
  }

  // 1. Business Profile Card
  const card = createElement("section", "card");
  const cardHeader = createElement("div", "card-header");
  cardHeader.appendChild(createElement("h2", "card-title", "Business Profile"));
  card.appendChild(cardHeader);

  const form = createElement("form", "form-stack");
  const grid = createElement("div", "form-grid");

  const fields = {
    name: createField({
      id: "biz-name",
      name: "name",
      label: "Business Name *",
      required: true,
      maxLength: 160,
      value: business?.name || "",
    }),
    legal_name: createField({
      id: "biz-legal-name",
      name: "legal_name",
      label: "Legal Name",
      maxLength: 200,
      value: business?.legal_name || "",
    }),
    email: createField({
      id: "biz-email",
      name: "email",
      label: "Billing Email",
      type: "email",
      maxLength: 254,
      value: business?.email || "",
    }),
    phone: createField({
      id: "biz-phone",
      name: "phone",
      label: "Phone",
      maxLength: 40,
      value: business?.phone || "",
    }),
    tax_id: createField({
      id: "biz-tax-id",
      name: "tax_id",
      label: "Tax / GST ID",
      maxLength: 64,
      value: business?.tax_id || "",
    }),
    currency_code: createField({
      id: "biz-currency",
      name: "currency_code",
      label: "Currency Code *",
      required: true,
      maxLength: 3,
      value: business?.currency_code || "USD",
      help: "3-letter ISO currency code (e.g. USD, INR, EUR).",
    }),
    invoice_prefix: createField({
      id: "biz-prefix",
      name: "invoice_prefix",
      label: "Invoice Prefix *",
      required: true,
      maxLength: 20,
      value: business?.invoice_prefix || "INV-",
    }),
    next_invoice_number: createField({
      id: "biz-next-num",
      name: "next_invoice_number",
      label: "Next Invoice Number *",
      type: "number",
      required: true,
      min: 1,
      value: String(business?.next_invoice_number ?? 1),
    }),
    address_line1: createField({
      id: "biz-addr1",
      name: "address_line1",
      label: "Address Line 1",
      maxLength: 200,
      fullWidth: true,
      value: business?.address_line1 || "",
    }),
    address_line2: createField({
      id: "biz-addr2",
      name: "address_line2",
      label: "Address Line 2",
      maxLength: 200,
      fullWidth: true,
      value: business?.address_line2 || "",
    }),
    city: createField({
      id: "biz-city",
      name: "city",
      label: "City",
      maxLength: 100,
      value: business?.city || "",
    }),
    state: createField({
      id: "biz-state",
      name: "state",
      label: "State / Province",
      maxLength: 100,
      value: business?.state || "",
    }),
    postal_code: createField({
      id: "biz-postal",
      name: "postal_code",
      label: "Postal Code",
      maxLength: 30,
      value: business?.postal_code || "",
    }),
    country: createField({
      id: "biz-country",
      name: "country",
      label: "Country",
      maxLength: 100,
      value: business?.country || "",
    }),
    bank_account_holder: createField({
      id: "biz-bank-holder",
      name: "bank_account_holder",
      label: "Bank Account Holder Name",
      maxLength: 160,
      value: business?.bank_account_holder || "",
    }),
    bank_name: createField({
      id: "biz-bank-name",
      name: "bank_name",
      label: "Bank Name",
      maxLength: 160,
      value: business?.bank_name || "",
    }),
    bank_account_number: createField({
      id: "biz-bank-acct",
      name: "bank_account_number",
      label: "Account Number",
      maxLength: 64,
      value: business?.bank_account_number || "",
    }),
    bank_ifsc_code: createField({
      id: "biz-bank-ifsc",
      name: "bank_ifsc_code",
      label: "IFSC Code",
      maxLength: 32,
      placeholder: "SBIN0001234",
      value: business?.bank_ifsc_code || "",
    }),
    bank_branch: createField({
      id: "biz-bank-branch",
      name: "bank_branch",
      label: "Bank Branch",
      maxLength: 160,
      value: business?.bank_branch || "",
    }),
    upi_id: createField({
      id: "biz-upi-id",
      name: "upi_id",
      label: "UPI ID (for Invoice Payment QR)",
      maxLength: 120,
      placeholder: "business@upi",
      value: business?.upi_id || "",
      help: "Used to generate amount-specific payment QR codes on invoices and PDFs.",
    }),
  };

  for (const field of Object.values(fields)) {
    grid.appendChild(field.wrapper);
  }

  const sigPlaceWrap = createElement("div", "form-field");
  const sigPlaceLabel = createElement("label", "form-label", "Invoice Signature Placement");
  sigPlaceLabel.setAttribute("for", "biz-sig-placement");
  const sigPlaceSelect = createElement("select", "form-input");
  sigPlaceSelect.id = "biz-sig-placement";
  for (const [val, label] of [
    ["bottom_right", "Bottom Right (Default)"],
    ["bottom_center", "Bottom Center"],
    ["bottom_left", "Bottom Left"],
  ]) {
    const opt = createElement("option", "", label);
    opt.value = val;
    if ((business?.signature_placement || "bottom_right") === val) opt.selected = true;
    sigPlaceSelect.appendChild(opt);
  }
  sigPlaceWrap.appendChild(sigPlaceLabel);
  sigPlaceWrap.appendChild(sigPlaceSelect);
  grid.appendChild(sigPlaceWrap);

  const sigEnabledField = createCheckboxField({
    id: "biz-sig-enabled",
    name: "signature_enabled",
    label: "Show visual signature on invoice previews and PDFs",
    checked: Boolean(business?.signature_enabled),
    fullWidth: true,
  });
  grid.appendChild(sigEnabledField.wrapper);

  form.appendChild(grid);

  const actions = createElement("div", "form-actions");
  const saveBtn = createElement(
    "button",
    "btn btn-primary",
    settingsState.saving ? "Saving Changes..." : "Save Business Settings"
  );
  saveBtn.type = "submit";
  saveBtn.disabled = Boolean(settingsState.saving);
  actions.appendChild(saveBtn);
  form.appendChild(actions);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const nextNumber = Number.parseInt(fields.next_invoice_number.input.value, 10);
    onSaveBusiness({
      name: fields.name.input.value.trim(),
      legal_name: fields.legal_name.input.value.trim() || null,
      email: fields.email.input.value.trim() || null,
      phone: fields.phone.input.value.trim() || null,
      tax_id: fields.tax_id.input.value.trim() || null,
      currency_code: fields.currency_code.input.value.trim().toUpperCase(),
      invoice_prefix: fields.invoice_prefix.input.value.trim(),
      next_invoice_number: Number.isNaN(nextNumber) ? 1 : nextNumber,
      address_line1: fields.address_line1.input.value.trim() || null,
      address_line2: fields.address_line2.input.value.trim() || null,
      city: fields.city.input.value.trim() || null,
      state: fields.state.input.value.trim() || null,
      postal_code: fields.postal_code.input.value.trim() || null,
      country: fields.country.input.value.trim() || null,
      bank_account_holder: fields.bank_account_holder.input.value.trim() || null,
      bank_name: fields.bank_name.input.value.trim() || null,
      bank_account_number: fields.bank_account_number.input.value.trim() || null,
      bank_ifsc_code: fields.bank_ifsc_code.input.value.trim().toUpperCase() || null,
      bank_branch: fields.bank_branch.input.value.trim() || null,
      upi_id: fields.upi_id.input.value.trim().toLowerCase() || null,
      signature_enabled: sigEnabledField.input.checked,
      signature_placement: sigPlaceSelect.value,
    });
  });

  card.appendChild(form);
  container.appendChild(card);

  // Dedicated Visual Signature Upload / Preview / Replace / Remove Card
  const sigCard = createElement("section", "card");
  const sigHeader = createElement("div", "card-header");
  sigHeader.appendChild(createElement("h2", "card-title", "Authorized Visual Signature"));
  sigCard.appendChild(sigHeader);

  sigCard.appendChild(
    createElement(
      "p",
      "section-subtitle",
      "Upload a visual signature image (PNG, JPG/JPEG, or WebP, max 2 MB) to appear in the Authorized Signatory section of your invoices. This is a visual image, not a cryptographic certificate."
    )
  );

  const previewBox = createElement("div", "signature-preview-box");
  if (business?.has_signature) {
    const img = document.createElement("img");
    img.className = "signature-preview-img";
    img.alt = "Configured business visual signature";
    img.src = `${getBusinessSignatureUrl()}?v=${encodeURIComponent(business.signature_updated_at || "")}`;
    previewBox.appendChild(img);
  } else {
    previewBox.appendChild(createElement("span", "cell-secondary", "No signature uploaded yet"));
  }
  sigCard.appendChild(previewBox);

  const sigControls = createElement("div", "signature-controls");
  const fileInput = document.createElement("input");
  fileInput.id = "biz-signature-file";
  fileInput.type = "file";
  fileInput.accept = "image/png,image/jpeg,image/webp";
  fileInput.className = "form-input";
  fileInput.style.maxWidth = "320px";
  fileInput.setAttribute("aria-label", "Choose signature image");

  const uploadBtn = createElement(
    "button",
    "btn btn-primary",
    settingsState.uploadingSignature
      ? "Uploading..."
      : business?.has_signature
      ? "Replace Signature"
      : "Upload Signature"
  );
  uploadBtn.type = "button";
  uploadBtn.disabled = Boolean(settingsState.uploadingSignature);
  uploadBtn.addEventListener("click", () => {
    const file = fileInput.files?.[0];
    if (!file) {
      onUploadSignature(null);
      return;
    }
    onUploadSignature(file);
  });

  sigControls.appendChild(fileInput);
  sigControls.appendChild(uploadBtn);

  if (business?.has_signature) {
    const removeBtn = createElement("button", "btn btn-danger-outline", "Remove Signature");
    removeBtn.type = "button";
    removeBtn.disabled = Boolean(settingsState.uploadingSignature);
    removeBtn.addEventListener("click", () => {
      openConfirmDialog({
        title: "Remove Visual Signature",
        message: "Remove the uploaded signature image and disable it on invoices?",
        confirmLabel: "Remove Signature",
        onConfirm: async () => {
          await onRemoveSignature();
        },
      });
    });
    sigControls.appendChild(removeBtn);
  }

  sigCard.appendChild(sigControls);
  container.appendChild(sigCard);

  // 2. Business Logo Management Card
  let pendingLogoObjectUrl = null;
  let refreshLivePreview = () => {};

  const logoCard = createElement("section", "card");
  const logoHeader = createElement("div", "card-header");
  logoHeader.appendChild(createElement("h2", "card-title", "Business Logo"));
  logoCard.appendChild(logoHeader);
  logoCard.appendChild(
    createElement(
      "p",
      "section-subtitle",
      "Upload your shop or company logo (PNG, JPG/JPEG, or WebP, max 2 MB). Displayed in the dashboard header, invoice previews, and PDF invoices while preserving aspect ratio."
    )
  );

  const logoPreviewBox = createElement("div", "signature-preview-box logo-preview-box");
  const logoPreviewHint = createElement("p", "form-help", "");

  function renderLogoBox(previewUrl, isPending) {
    logoPreviewBox.replaceChildren();
    if (previewUrl) {
      const img = document.createElement("img");
      img.className = "logo-preview-img";
      img.alt = isPending ? "Selected logo preview (not yet saved)" : "Configured business logo";
      img.src = previewUrl;
      img.addEventListener("error", () => {
        logoPreviewBox.replaceChildren(
          createElement("span", "cell-secondary", "Unable to display logo image")
        );
      });
      logoPreviewBox.appendChild(img);
      logoPreviewHint.textContent = isPending
        ? "Preview ready — click Upload / Replace Logo to save this logo."
        : "Saved business logo active across header, invoice preview, and PDFs.";
    } else {
      logoPreviewBox.appendChild(
        createElement("span", "cell-secondary", "No business logo uploaded yet")
      );
      logoPreviewHint.textContent = "Invoices render cleanly with text header until a logo is uploaded.";
    }
  }

  const savedLogoUrl = business?.has_logo
    ? `${getBusinessLogoUrl()}?v=${encodeURIComponent(business.logo_updated_at || "")}`
    : null;
  renderLogoBox(savedLogoUrl, false);
  logoCard.appendChild(logoPreviewBox);
  logoCard.appendChild(logoPreviewHint);

  const logoControls = createElement("div", "signature-controls");
  const logoFileInput = document.createElement("input");
  logoFileInput.id = "biz-logo-file";
  logoFileInput.type = "file";
  logoFileInput.accept = "image/png,image/jpeg,image/webp";
  logoFileInput.className = "form-input";
  logoFileInput.style.maxWidth = "320px";
  logoFileInput.setAttribute("aria-label", "Choose business logo image");

  logoFileInput.addEventListener("change", () => {
    if (pendingLogoObjectUrl) {
      URL.revokeObjectURL(pendingLogoObjectUrl);
      pendingLogoObjectUrl = null;
    }
    const file = logoFileInput.files?.[0];
    if (file) {
      pendingLogoObjectUrl = URL.createObjectURL(file);
      renderLogoBox(pendingLogoObjectUrl, true);
    } else {
      renderLogoBox(savedLogoUrl, false);
    }
    refreshLivePreview();
  });

  const logoUploadBtn = createElement(
    "button",
    "btn btn-primary",
    settingsState.uploadingLogo
      ? "Uploading..."
      : business?.has_logo
      ? "Replace Logo"
      : "Upload Logo"
  );
  logoUploadBtn.type = "button";
  logoUploadBtn.disabled = Boolean(settingsState.uploadingLogo);
  logoUploadBtn.addEventListener("click", () => {
    const file = logoFileInput.files?.[0] || null;
    onUploadLogo(file, Boolean(business?.has_logo));
  });

  logoControls.appendChild(logoFileInput);
  logoControls.appendChild(logoUploadBtn);

  if (business?.has_logo) {
    const removeLogoBtn = createElement("button", "btn btn-danger-outline", "Remove Logo");
    removeLogoBtn.type = "button";
    removeLogoBtn.disabled = Boolean(settingsState.uploadingLogo);
    removeLogoBtn.addEventListener("click", () => {
      openConfirmDialog({
        title: "Remove Business Logo",
        message: "Remove the uploaded business logo from dashboard headers and future invoices?",
        confirmLabel: "Remove Logo",
        onConfirm: async () => {
          await onRemoveLogo();
        },
      });
    });
    logoControls.appendChild(removeLogoBtn);
  }

  logoCard.appendChild(logoControls);
  container.insertBefore(logoCard, sigCard);

  // 4. Invoice Appearance / Invoice Theme Card
  const presets = Array.isArray(themePresets) && themePresets.length > 0
    ? themePresets
    : INVOICE_THEME_PRESETS;
  const draftTheme = extractThemeFromBusiness(business);

  const themeCard = createElement("section", "card");
  const themeHeader = createElement("div", "card-header");
  themeHeader.appendChild(createElement("h2", "card-title", "Invoice Appearance / Invoice Theme"));
  themeCard.appendChild(themeHeader);
  themeCard.appendChild(
    createElement(
      "p",
      "section-subtitle",
      "Choose a ready-made invoice theme preset or customize individual colors. Changes preview live below and apply consistently to invoice previews, printed sheets, and generated PDFs."
    )
  );

  const presetsSection = createElement("div", "theme-subsection");
  presetsSection.appendChild(createElement("h3", "theme-subheading", "Invoice Theme Presets"));
  const presetsGrid = createElement("div", "theme-presets-grid");
  const presetCards = [];

  const colorSection = createElement("div", "theme-subsection");
  colorSection.appendChild(createElement("h3", "theme-subheading", "Custom Colors"));
  const colorGrid = createElement("div", "theme-colors-grid");

  const previewSection = createElement("div", "theme-subsection");
  previewSection.appendChild(createElement("h3", "theme-subheading", "Live Preview"));
  const livePreviewHost = createElement("div", "theme-live-preview-host");
  previewSection.appendChild(livePreviewHost);

  refreshLivePreview = () => {
    renderSampleInvoicePreview(livePreviewHost, {
      business,
      theme: draftTheme,
      pendingLogoUrl: pendingLogoObjectUrl,
    });
  };

  function syncPresetActiveStates() {
    for (const item of presetCards) {
      const isSelected = draftTheme.preset === item.key;
      item.el.classList.toggle("is-selected", isSelected);
      item.el.setAttribute("aria-pressed", String(isSelected));
    }
  }

  const colorFieldSpecs = [
    ["primary_color", "Primary Invoice Color"],
    ["secondary_color", "Secondary Color"],
    ["accent_color", "Accent Color"],
    ["header_color", "Header / Background Color"],
    ["table_header_color", "Table Header Color"],
    ["text_color", "Text Color"],
    ["border_color", "Border Color"],
  ];
  const colorControls = {};

  function syncColorInputs() {
    for (const [fieldKey] of colorFieldSpecs) {
      const ctrl = colorControls[fieldKey];
      if (!ctrl) continue;
      const val = normalizeHex(draftTheme[fieldKey]);
      ctrl.colorInput.value = val;
      ctrl.hexInput.value = val;
    }
  }

  for (const preset of presets) {
    const pCard = createElement("button", "theme-preset-card");
    pCard.type = "button";
    pCard.dataset.preset = preset.key;

    const swatches = createElement("div", "theme-swatch-strip");
    for (const swatchHex of [
      preset.primary_color,
      preset.secondary_color,
      preset.table_header_color,
      preset.header_color,
      preset.accent_color,
    ]) {
      const dot = createElement("span", "theme-swatch-dot");
      dot.style.backgroundColor = swatchHex;
      swatches.appendChild(dot);
    }

    pCard.appendChild(swatches);
    pCard.appendChild(createElement("span", "theme-preset-name", preset.name));
    pCard.appendChild(createElement("span", "theme-preset-desc", preset.description || ""));

    pCard.addEventListener("click", () => {
      draftTheme.preset = preset.key;
      for (const [k] of colorFieldSpecs) {
        draftTheme[k] = normalizeHex(preset[k]);
      }
      syncPresetActiveStates();
      syncColorInputs();
      refreshLivePreview();
    });

    presetCards.push({ key: preset.key, el: pCard });
    presetsGrid.appendChild(pCard);
  }
  presetsSection.appendChild(presetsGrid);

  for (const [fieldKey, labelText] of colorFieldSpecs) {
    const cell = createElement("div", "theme-color-field");
    const lbl = createElement("label", "form-label", labelText);
    const inputId = `theme-${fieldKey}`;
    lbl.setAttribute("for", `${inputId}-hex`);

    const row = createElement("div", "theme-color-inputs");
    const colorInput = document.createElement("input");
    colorInput.type = "color";
    colorInput.id = inputId;
    colorInput.className = "theme-color-picker";
    colorInput.value = normalizeHex(draftTheme[fieldKey]);
    colorInput.setAttribute("aria-label", `${labelText} picker`);

    const hexInput = document.createElement("input");
    hexInput.type = "text";
    hexInput.id = `${inputId}-hex`;
    hexInput.className = "form-input theme-hex-input";
    hexInput.maxLength = 7;
    hexInput.value = normalizeHex(draftTheme[fieldKey]);
    hexInput.placeholder = "#2563EB";

    colorInput.addEventListener("input", () => {
      const normalized = normalizeHex(colorInput.value);
      draftTheme[fieldKey] = normalized;
      draftTheme.preset = "custom";
      hexInput.value = normalized;
      syncPresetActiveStates();
      refreshLivePreview();
    });

    hexInput.addEventListener("input", () => {
      const raw = hexInput.value.trim().toUpperCase();
      if (/^#[0-9A-F]{6}$/.test(raw)) {
        draftTheme[fieldKey] = raw;
        draftTheme.preset = "custom";
        colorInput.value = raw;
        syncPresetActiveStates();
        refreshLivePreview();
      }
    });

    hexInput.addEventListener("blur", () => {
      hexInput.value = normalizeHex(draftTheme[fieldKey]);
    });

    row.appendChild(colorInput);
    row.appendChild(hexInput);
    cell.appendChild(lbl);
    cell.appendChild(row);
    colorGrid.appendChild(cell);
    colorControls[fieldKey] = { colorInput, hexInput };
  }
  colorSection.appendChild(colorGrid);

  const themeActions = createElement("div", "form-actions theme-actions-bar");
  const resetThemeBtn = createElement("button", "btn", "Reset to Default");
  resetThemeBtn.type = "button";
  resetThemeBtn.disabled = Boolean(settingsState.savingTheme);
  resetThemeBtn.addEventListener("click", () => {
    draftTheme.preset = DEFAULT_THEME.key;
    for (const [k] of colorFieldSpecs) {
      draftTheme[k] = normalizeHex(DEFAULT_THEME[k]);
    }
    syncPresetActiveStates();
    syncColorInputs();
    refreshLivePreview();
  });

  const saveThemeBtn = createElement(
    "button",
    "btn btn-primary",
    settingsState.savingTheme ? "Saving Theme..." : "Save Theme Settings"
  );
  saveThemeBtn.type = "button";
  saveThemeBtn.disabled = Boolean(settingsState.savingTheme);
  saveThemeBtn.addEventListener("click", () => {
    onSaveTheme({
      preset: draftTheme.preset || "custom",
      primary_color: normalizeHex(draftTheme.primary_color),
      secondary_color: normalizeHex(draftTheme.secondary_color),
      accent_color: normalizeHex(draftTheme.accent_color),
      header_color: normalizeHex(draftTheme.header_color),
      table_header_color: normalizeHex(draftTheme.table_header_color),
      text_color: normalizeHex(draftTheme.text_color),
      border_color: normalizeHex(draftTheme.border_color),
    });
  });

  themeActions.appendChild(resetThemeBtn);
  themeActions.appendChild(saveThemeBtn);

  const appearanceLayout = createElement("div", "appearance-layout");
  const controlsCol = createElement("div", "appearance-controls-col");
  controlsCol.appendChild(presetsSection);
  controlsCol.appendChild(colorSection);
  controlsCol.appendChild(themeActions);

  appearanceLayout.appendChild(controlsCol);
  appearanceLayout.appendChild(previewSection);
  themeCard.appendChild(appearanceLayout);

  syncPresetActiveStates();
  refreshLivePreview();
  container.appendChild(themeCard);

  // 5. Account Security — Change Password Card
  const secCard = createElement("section", "card");
  secCard.appendChild(createElement("h2", "card-title", "Account Security — Change Password"));
  secCard.appendChild(
    createElement(
      "p",
      "section-subtitle",
      "Update your account login password. Active other sessions remain protected."
    )
  );
  const pwdErr = createElement("div", "alert alert-error is-hidden");
  pwdErr.setAttribute("role", "alert");
  const pwdOk = createElement("div", "alert alert-success is-hidden");
  pwdOk.setAttribute("role", "status");
  const pwdForm = createElement("form", "form-grid");
  const curPwd = createField({
    id: "set-cur-pwd",
    name: "current_password",
    label: "Current Password *",
    type: "password",
    required: true,
    autocomplete: "current-password",
  });
  const newPwd = createField({
    id: "set-new-pwd",
    name: "new_password",
    label: "New Password *",
    type: "password",
    required: true,
    autocomplete: "new-password",
    help: "Minimum 8 characters.",
  });
  const confPwd = createField({
    id: "set-conf-pwd",
    name: "confirm_password",
    label: "Confirm New Password *",
    type: "password",
    required: true,
    autocomplete: "new-password",
  });
  const pwdActions = createElement("div", "form-actions form-field-full");
  const savePwdBtn = createElement("button", "btn btn-primary", "Update Password");
  savePwdBtn.type = "submit";
  pwdActions.appendChild(savePwdBtn);
  pwdForm.append(curPwd.wrapper, newPwd.wrapper, confPwd.wrapper, pwdActions);
  pwdForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    pwdErr.classList.add("is-hidden");
    pwdOk.classList.add("is-hidden");
    if (newPwd.input.value !== confPwd.input.value) {
      pwdErr.textContent = "New Password and Confirm Password do not match.";
      pwdErr.classList.remove("is-hidden");
      return;
    }
    savePwdBtn.disabled = true;
    savePwdBtn.textContent = "Updating...";
    try {
      await changeUserPassword({
        current_password: curPwd.input.value,
        new_password: newPwd.input.value,
        confirm_password: confPwd.input.value,
      });
      pwdForm.reset();
      pwdOk.textContent = "Account password updated successfully.";
      pwdOk.classList.remove("is-hidden");
      showToast("Password updated.", "success");
    } catch (err) {
      pwdErr.textContent = err instanceof Error ? err.message : "Failed to update password.";
      pwdErr.classList.remove("is-hidden");
    } finally {
      savePwdBtn.disabled = false;
      savePwdBtn.textContent = "Update Password";
    }
  });
  secCard.append(pwdErr, pwdOk, pwdForm);
  container.appendChild(secCard);
}

export function renderSection(
  container,
  sectionKey,
  {
    healthState,
    session,
    counts,
    supportInfo,
    settingsState,
    themePresets,
    onNavigate,
    onSaveBusiness,
    onUploadSignature,
    onRemoveSignature,
    onUploadLogo,
    onRemoveLogo,
    onSaveTheme,
  }
) {
  const meta = SECTION_META[sectionKey] || SECTION_META.dashboard;
  container.replaceChildren();

  const header = createElement("div", "section-header");
  const headingWrap = createElement("div");
  headingWrap.appendChild(createElement("h2", "section-heading", meta.title));
  headingWrap.appendChild(createElement("p", "section-subtitle", meta.subtitle));
  header.appendChild(headingWrap);
  container.appendChild(header);

  if (sectionKey === "settings") {
    renderBusinessSettingsSection(container, {
      business: session?.business,
      settingsState,
      themePresets,
      onSaveBusiness,
      onUploadSignature,
      onRemoveSignature,
      onUploadLogo,
      onRemoveLogo,
      onSaveTheme,
    });
    return;
  }

  if (sectionKey === "dashboard") {
    const business = session?.business;
    const metricsGrid = createElement("section", "metrics-grid");
    metricsGrid.setAttribute("aria-label", "Summary metrics");

    const cur = business?.currency_code || "USD";
    const summary = counts?.summary;
    const metrics = [
      {
        label: "Total Billed",
        value: summary ? formatCurrency(summary.total_billed, cur) : "—",
        helper: `${counts?.invoices ?? 0} total invoices`,
      },
      {
        label: "Outstanding Balance",
        value: summary ? formatCurrency(summary.total_outstanding, cur) : "—",
        helper: summary ? `${summary.overdue_count} overdue` : "Across open invoices",
      },
      {
        label: "Payments Collected",
        value: summary ? formatCurrency(summary.total_collected_payments, cur) : "—",
        helper: "Recorded in Payments",
      },
      {
        label: "Customers & Catalog",
        value: `${counts?.customers ?? 0} / ${counts?.products ?? 0}`,
        helper: "Active customers / items",
      },
    ];

    for (const metric of metrics) {
      const card = createElement("article", "card");
      card.appendChild(createElement("p", "metric-label", metric.label));
      card.appendChild(createElement("p", "metric-value", metric.value));
      card.appendChild(createElement("p", "metric-helper", metric.helper));
      metricsGrid.appendChild(card);
    }
    container.appendChild(metricsGrid);

    if (session?.subscription) {
      container.appendChild(
        buildSubscriptionSummaryCard({
          subscription: session.subscription,
          supportInfo,
          onNavigate,
          compact: true,
        })
      );
    }

    const contentGrid = createElement("div", "content-grid");

    const recentCard = createElement("section", "card");
    const recentHeader = createElement("div", "card-header");
    recentHeader.appendChild(createElement("h2", "card-title", "Recent Invoices"));
    const allInvBtn = createElement("button", "btn btn-sm", "View All");
    allInvBtn.type = "button";
    allInvBtn.addEventListener("click", () => onNavigate("invoices"));
    recentHeader.appendChild(allInvBtn);
    recentCard.appendChild(recentHeader);

    const recentInvoices = counts?.recentInvoices || [];
    if (recentInvoices.length === 0) {
      const empty = createElement("div", "empty-state");
      empty.appendChild(createElement("h3", "empty-state-title", meta.emptyTitle));
      empty.appendChild(createElement("p", "empty-state-text", meta.emptyText));
      const newInvBtn = createElement("button", "btn btn-primary", "Create First Invoice");
      newInvBtn.type = "button";
      newInvBtn.addEventListener("click", () => onNavigate("invoices-new"));
      empty.appendChild(newInvBtn);
      recentCard.appendChild(empty);
    } else {
      const scroll = createElement("div", "table-scroll");
      const table = createElement("table", "data-table");
      const thead = createElement("thead");
      const headRow = createElement("tr");
      for (const [lbl, cls] of [
        ["Invoice #", ""],
        ["Customer", ""],
        ["Status", ""],
        ["Total", "cell-numeric"],
      ]) {
        headRow.appendChild(createElement("th", cls, lbl));
      }
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = createElement("tbody");
      for (const inv of recentInvoices) {
        const row = createElement("tr");
        const numTd = createElement("td");
        const openBtn = createElement("button", "btn btn-sm", inv.invoice_number);
        openBtn.type = "button";
        openBtn.addEventListener("click", () => onNavigate(`invoice:${inv.id}`));
        numTd.appendChild(openBtn);

        row.appendChild(numTd);
        row.appendChild(createElement("td", "", inv.customer?.name || "—"));
        const stTd = createElement("td");
        stTd.appendChild(
          createElement(
            "span",
            `badge badge-${inv.effective_status || "draft"}`,
            String(inv.effective_status || "draft").replace("_", " ")
          )
        );
        row.appendChild(stTd);
        row.appendChild(
          createElement("td", "cell-numeric", formatCurrency(inv.total_amount, inv.currency_code))
        );
        tbody.appendChild(row);
      }
      table.appendChild(tbody);
      scroll.appendChild(table);
      recentCard.appendChild(scroll);
    }

    const sideStack = createElement("div", "quick-actions-list");
    const actionsCard = createElement("section", "card");
    const actionsHeader = createElement("div", "card-header");
    actionsHeader.appendChild(createElement("h2", "card-title", "Quick Actions"));
    actionsCard.appendChild(actionsHeader);

    const actionButtonsWrap = createElement("div", "quick-actions-list");
    const quickLinks = [
      { label: "+ Create Invoice", target: "invoices-new" },
      { label: "Record Payment", target: "payments" },
      { label: "View Sales Reports", target: "reports" },
      { label: "Manage Customers", target: "customers" },
      { label: "Manage Products / Services", target: "products" },
      { label: "Inventory / Stock Levels", target: "inventory" },
      { label: "Notifications & Alerts", target: "notifications" },
      { label: "Subscription & Plan", target: "subscription" },
      { label: "Activate Subscription Code", target: "activation" },
      { label: "Edit Business Settings", target: "settings" },
    ];
    for (const action of quickLinks) {
      const btn = createElement("button", "btn", action.label);
      btn.type = "button";
      btn.addEventListener("click", () => onNavigate(action.target));
      actionButtonsWrap.appendChild(btn);
    }
    actionsCard.appendChild(actionButtonsWrap);

    sideStack.appendChild(actionsCard);
    sideStack.appendChild(buildHealthCard(healthState));

    contentGrid.appendChild(recentCard);
    contentGrid.appendChild(sideStack);
    container.appendChild(contentGrid);
    return;
  }

  const card = createElement("section", "card");
  const empty = createElement("div", "empty-state");
  empty.appendChild(createElement("h3", "empty-state-title", meta.emptyTitle));
  empty.appendChild(createElement("p", "empty-state-text", meta.emptyText));

  const backBtn = createElement("button", "btn", "Back to Dashboard");
  backBtn.type = "button";
  backBtn.addEventListener("click", () => onNavigate("dashboard"));
  empty.appendChild(backBtn);

  card.appendChild(empty);
  container.appendChild(card);
}
