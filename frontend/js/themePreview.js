/**
 * Invoice theme presets, contrast CSS variable application, and live Settings invoice preview.
 */

import { getBusinessLogoUrl, getBusinessSignatureUrl } from "/js/api.js";
import { createElement, formatCurrency } from "/js/dom.js";

export const INVOICE_THEME_PRESETS = [
  {
    key: "classic_blue",
    name: "Classic Blue",
    description: "Crisp corporate blue accents on clean white surfaces.",
    primary_color: "#2563EB",
    secondary_color: "#1E40AF",
    accent_color: "#EFF6FF",
    header_color: "#F8FAFC",
    table_header_color: "#EFF6FF",
    text_color: "#172033",
    border_color: "#E2E8F0",
  },
  {
    key: "elegant_black",
    name: "Elegant Black",
    description: "High-contrast charcoal monochrome for executive invoices.",
    primary_color: "#111827",
    secondary_color: "#374151",
    accent_color: "#F3F4F6",
    header_color: "#F9FAFB",
    table_header_color: "#111827",
    text_color: "#111827",
    border_color: "#D1D5DB",
  },
  {
    key: "emerald_green",
    name: "Emerald Green",
    description: "Fresh emerald highlights suited for modern service firms.",
    primary_color: "#059669",
    secondary_color: "#065F46",
    accent_color: "#ECFDF5",
    header_color: "#F0FDF4",
    table_header_color: "#D1FAE5",
    text_color: "#14281D",
    border_color: "#A7F3D0",
  },
  {
    key: "royal_purple",
    name: "Royal Purple",
    description: "Refined indigo-violet accents for creative & tech brands.",
    primary_color: "#7C3AED",
    secondary_color: "#5B21B6",
    accent_color: "#F5F3FF",
    header_color: "#FAF5FF",
    table_header_color: "#EDE9FE",
    text_color: "#1E1B4B",
    border_color: "#DDD6FE",
  },
  {
    key: "modern_orange",
    name: "Modern Orange",
    description: "Warm amber-orange palette with sharp readable slate type.",
    primary_color: "#EA580C",
    secondary_color: "#9A3412",
    accent_color: "#FFF7ED",
    header_color: "#FFFBEB",
    table_header_color: "#FFEDD5",
    text_color: "#1C1917",
    border_color: "#FED7AA",
  },
  {
    key: "minimal_grey",
    name: "Minimal Grey",
    description: "Neutral slate tones with distraction-free print clarity.",
    primary_color: "#475569",
    secondary_color: "#334155",
    accent_color: "#F8FAFC",
    header_color: "#F1F5F9",
    table_header_color: "#E2E8F0",
    text_color: "#0F172A",
    border_color: "#CBD5E1",
  },
  {
    key: "crimson_red",
    name: "Crimson Red",
    description: "Bold crimson header highlights with balanced rose tints.",
    primary_color: "#DC2626",
    secondary_color: "#991B1B",
    accent_color: "#FEF2F2",
    header_color: "#FFF5F5",
    table_header_color: "#FEE2E2",
    text_color: "#1F2937",
    border_color: "#FECACA",
  },
  {
    key: "teal_professional",
    name: "Teal Professional",
    description: "Structured ocean teal header with calm neutral framing.",
    primary_color: "#0D9488",
    secondary_color: "#115E59",
    accent_color: "#F0FDFA",
    header_color: "#F0FDFA",
    table_header_color: "#0F766E",
    text_color: "#134E4A",
    border_color: "#99F6E4",
  },
];

export const DEFAULT_THEME = { ...INVOICE_THEME_PRESETS[0] };

export function normalizeHex(value, fallback = "#2563EB") {
  const cleaned = String(value || "").trim().toUpperCase();
  return /^#[0-9A-F]{6}$/.test(cleaned) ? cleaned : fallback;
}

function hexLuminance(hex) {
  const safe = normalizeHex(hex, "#FFFFFF").slice(1);
  const r = Number.parseInt(safe.slice(0, 2), 16) / 255;
  const g = Number.parseInt(safe.slice(2, 4), 16) / 255;
  const b = Number.parseInt(safe.slice(4, 6), 16) / 255;
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

export function contrastColorFor(bgHex, lightText = "#FFFFFF", darkText = "#172033") {
  return hexLuminance(bgHex) < 0.54 ? lightText : darkText;
}

export function extractThemeFromBusiness(business) {
  return {
    preset: business?.invoice_theme_preset || DEFAULT_THEME.key,
    primary_color: normalizeHex(business?.theme_primary_color, DEFAULT_THEME.primary_color),
    secondary_color: normalizeHex(business?.theme_secondary_color, DEFAULT_THEME.secondary_color),
    accent_color: normalizeHex(business?.theme_accent_color, DEFAULT_THEME.accent_color),
    header_color: normalizeHex(business?.theme_header_color, DEFAULT_THEME.header_color),
    table_header_color: normalizeHex(
      business?.theme_table_header_color,
      DEFAULT_THEME.table_header_color
    ),
    text_color: normalizeHex(business?.theme_text_color, DEFAULT_THEME.text_color),
    border_color: normalizeHex(business?.theme_border_color, DEFAULT_THEME.border_color),
  };
}

export function applyInvoiceThemeVariables(targetEl, theme) {
  const t = theme || DEFAULT_THEME;
  const primary = normalizeHex(t.primary_color, DEFAULT_THEME.primary_color);
  const secondary = normalizeHex(t.secondary_color, DEFAULT_THEME.secondary_color);
  const accent = normalizeHex(t.accent_color, DEFAULT_THEME.accent_color);
  const header = normalizeHex(t.header_color, DEFAULT_THEME.header_color);
  const tableHeader = normalizeHex(t.table_header_color, DEFAULT_THEME.table_header_color);
  const text = normalizeHex(t.text_color, DEFAULT_THEME.text_color);
  const border = normalizeHex(t.border_color, DEFAULT_THEME.border_color);

  const headerText = contrastColorFor(header, "#FFFFFF", text);
  const headerMuted = contrastColorFor(header, "#E2E8F0", "#475569");
  const headerTitle =
    Math.abs(hexLuminance(primary) - hexLuminance(header)) < 0.28 ? headerText : primary;
  const tableHeaderText = contrastColorFor(tableHeader, "#FFFFFF", text);
  const accentText = contrastColorFor(accent, "#FFFFFF", text);
  const accentTitle =
    Math.abs(hexLuminance(primary) - hexLuminance(accent)) < 0.28 ? accentText : primary;

  targetEl.style.setProperty("--inv-primary", primary);
  targetEl.style.setProperty("--inv-secondary", secondary);
  targetEl.style.setProperty("--inv-accent", accent);
  targetEl.style.setProperty("--inv-header", header);
  targetEl.style.setProperty("--inv-header-text", headerText);
  targetEl.style.setProperty("--inv-header-muted", headerMuted);
  targetEl.style.setProperty("--inv-header-title", headerTitle);
  targetEl.style.setProperty("--inv-table-header", tableHeader);
  targetEl.style.setProperty("--inv-table-header-text", tableHeaderText);
  targetEl.style.setProperty("--inv-accent-text", accentText);
  targetEl.style.setProperty("--inv-accent-title", accentTitle);
  targetEl.style.setProperty("--inv-text", text);
  targetEl.style.setProperty("--inv-border", border);
}

export function renderSampleInvoicePreview(
  container,
  { business, theme, pendingLogoUrl = null }
) {
  container.replaceChildren();
  const sheet = createElement("article", "invoice-sheet invoice-sheet-sample");
  applyInvoiceThemeVariables(sheet, theme);

  const cur = business?.currency_code || "INR";
  const prefix = business?.invoice_prefix || "INV-";
  const num = String(business?.next_invoice_number ?? 1).padStart(4, "0");

  // Header
  const sheetHeader = createElement("div", "invoice-sheet-header");
  const bizWrap = createElement("div", "invoice-sheet-brand-wrap");

  const resolvedLogoSrc =
    pendingLogoUrl ||
    (business?.has_logo
      ? `${getBusinessLogoUrl()}?v=${encodeURIComponent(business.logo_updated_at || "")}`
      : null);
  if (resolvedLogoSrc) {
    const logoImg = document.createElement("img");
    logoImg.className = "invoice-sheet-logo";
    logoImg.alt = "Business Logo";
    logoImg.src = resolvedLogoSrc;
    logoImg.addEventListener("error", () => logoImg.remove());
    bizWrap.appendChild(logoImg);
  }

  const bizTextCol = createElement("div");
  bizTextCol.appendChild(
    createElement("h3", "invoice-sheet-brand", business?.name || "Your Business Name")
  );
  const bizMetaLines = [
    business?.address_line1 || "42 Commerce Avenue, Suite 300",
    [business?.city || "Mumbai", business?.state || "Maharashtra", business?.postal_code || "400001"]
      .filter(Boolean)
      .join(", "),
    `Tax / GSTIN: ${business?.tax_id || "27AABCU9603R1ZM"}`,
  ];
  bizTextCol.appendChild(createElement("p", "invoice-header-subtext", bizMetaLines.join("\n")));
  bizWrap.appendChild(bizTextCol);

  const metaCol = createElement("div");
  metaCol.appendChild(createElement("h3", "invoice-sheet-title", "INVOICE"));
  const metaList = createElement("div", "invoice-sheet-meta");
  for (const [k, v] of [
    ["Invoice #", `${prefix}${num}`],
    ["Issue Date", "2026-11-26"],
    ["GST Mode", "CGST + SGST"],
  ]) {
    const row = createElement("div");
    row.appendChild(createElement("span", "", `${k}: `));
    row.appendChild(createElement("strong", "", v));
    metaList.appendChild(row);
  }
  metaCol.appendChild(metaList);
  sheetHeader.appendChild(bizWrap);
  sheetHeader.appendChild(metaCol);
  sheet.appendChild(sheetHeader);

  // Bill To
  const parties = createElement("div", "invoice-sheet-parties");
  const billTo = createElement("div");
  billTo.appendChild(createElement("p", "invoice-party-label", "Bill To"));
  billTo.appendChild(
    createElement(
      "p",
      "invoice-party-text",
      "Aarav Traders LLP\nPlot 14, Tech Park, Bengaluru, Karnataka\nTax ID / GSTIN: 29AAACB2894G1ZV"
    )
  );
  parties.appendChild(billTo);
  sheet.appendChild(parties);

  // Sample Product Table
  const scroll = createElement("div", "table-scroll");
  const table = createElement("table", "data-table");
  const thead = createElement("thead");
  const headRow = createElement("tr");
  for (const [lbl, cls] of [
    ["Item", ""],
    ["HSN", ""],
    ["Qty", "cell-numeric"],
    ["Rate", "cell-numeric"],
    ["GST", "cell-numeric"],
    ["Total", "cell-numeric"],
  ]) {
    headRow.appendChild(createElement("th", cls, lbl));
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = createElement("tbody");
  const sampleRows = [
    ["Cloud Billing Setup", "998314", "1.00", formatCurrency(10000, cur), "18%", formatCurrency(11800, cur)],
    ["Support Plan", "998313", "2.00", formatCurrency(2500, cur), "18%", formatCurrency(5900, cur)],
  ];
  for (const rowData of sampleRows) {
    const tr = createElement("tr");
    rowData.forEach((cellVal, idx) => {
      tr.appendChild(createElement("td", idx >= 2 ? "cell-numeric" : "", cellVal));
    });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  scroll.appendChild(table);
  sheet.appendChild(scroll);

  // Totals
  const totalsBox = createElement("div", "totals-summary");
  for (const [lbl, val, isGrand] of [
    ["Subtotal", formatCurrency(15000, cur), false],
    ["CGST (9%) + SGST (9%)", formatCurrency(2700, cur), false],
    ["Grand Total", formatCurrency(17700, cur), true],
  ]) {
    const r = createElement("div", isGrand ? "totals-row totals-row-grand" : "totals-row");
    r.appendChild(createElement("span", "", lbl));
    r.appendChild(createElement("span", "", val));
    totalsBox.appendChild(r);
  }
  sheet.appendChild(totalsBox);

  // Bank & Signature Footer
  const footerGrid = createElement("div", "invoice-preview-footer");
  const bankCol = createElement("div");
  bankCol.appendChild(createElement("p", "invoice-party-label", "Bank & Payment Details"));
  const bankLines = [
    business?.bank_name ? `Bank: ${business.bank_name}` : "Bank: State Bank of India",
    business?.bank_account_number
      ? `A/C: ${business.bank_account_number}`
      : "A/C: 300012345678",
    business?.upi_id ? `UPI: ${business.upi_id}` : "UPI: billing@upi",
  ];
  bankCol.appendChild(createElement("p", "invoice-party-text", bankLines.join("\n")));
  footerGrid.appendChild(bankCol);

  if (business?.has_signature && business?.signature_enabled) {
    const sigBox = createElement("div", "invoice-signature-box");
    sigBox.appendChild(createElement("span", "cell-secondary", `For ${business.name || "Business"}`));
    const sigImg = document.createElement("img");
    sigImg.className = "invoice-signature-img";
    sigImg.alt = "Authorized Signatory";
    sigImg.src = `${getBusinessSignatureUrl()}?v=${encodeURIComponent(
      business.signature_updated_at || ""
    )}`;
    sigImg.addEventListener("error", () => sigImg.remove());
    sigBox.appendChild(sigImg);
    sigBox.appendChild(createElement("strong", "", "Authorized Signatory"));
    footerGrid.appendChild(sigBox);
  } else {
    const stampBox = createElement("div", "invoice-signature-box");
    stampBox.appendChild(createElement("span", "cell-secondary", "Authorized Signatory / Stamp"));
    stampBox.appendChild(
      createElement("span", "cell-secondary", `For ${business?.name || "Your Business"}`)
    );
    footerGrid.appendChild(stampBox);
  }

  sheet.appendChild(footerGrid);
  container.appendChild(sheet);
}
