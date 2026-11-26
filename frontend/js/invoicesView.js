/**
 * Invoices management view: list, edit (draft & unpaid issued), GST split, HSN, QR, and history.
 */

import {
  createInvoice,
  deleteInvoice,
  duplicateInvoice,
  fetchCustomers,
  fetchInvoice,
  fetchInvoices,
  fetchProducts,
  getBusinessLogoUrl,
  getBusinessSignatureUrl,
  getInvoicePdfUrl,
  getInvoiceQrUrl,
  issueInvoice,
  updateInvoice,
  voidInvoice,
} from "/js/api.js";
import {
  createElement,
  createField,
  formatCurrency,
  renderPaginationBar,
  showToast,
} from "/js/dom.js";
import { openConfirmDialog, openModal } from "/js/modal.js";
import { openRecordPaymentModal } from "/js/paymentsView.js";
import { applyInvoiceThemeVariables, extractThemeFromBusiness } from "/js/themePreview.js";

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function addDaysIso(days) {
  const dt = new Date();
  dt.setDate(dt.getDate() + days);
  return dt.toISOString().slice(0, 10);
}

function roundMoney(num) {
  return Math.round((num + Number.EPSILON) * 100) / 100;
}

function resolvePreviewGstType(gstMode, business, customer) {
  if (gstMode === "cgst_sgst" || gstMode === "igst") return gstMode;
  const bizState = (business?.state || "").trim().toLowerCase();
  const custState = (customer?.state || "").trim().toLowerCase();
  if (bizState && custState && bizState !== custState) return "igst";
  return "cgst_sgst";
}

function computePreviewLine(line, gstType) {
  const qty = Number(line.quantity) || 0;
  const price = Number(line.unit_price) || 0;
  const discPct = Number(line.discount_percent) || 0;
  const taxRate = Number(line.tax_rate) || 0;
  const subtotal = roundMoney(qty * price);
  const discount = roundMoney((subtotal * discPct) / 100);
  const taxable = subtotal - discount;
  const tax = roundMoney((taxable * taxRate) / 100);
  const cgst = gstType === "igst" ? 0 : roundMoney(tax / 2);
  const sgst = gstType === "igst" ? 0 : roundMoney(tax - cgst);
  const igst = gstType === "igst" ? tax : 0;
  return { subtotal, discount, cgst, sgst, igst, tax, total: roundMoney(taxable + tax) };
}

function statusBadge(status) {
  const label = String(status || "draft").replace("_", " ");
  const formatted = label.charAt(0).toUpperCase() + label.slice(1);
  return createElement("span", `badge badge-${status || "draft"}`, formatted);
}

function openCancelInvoiceDialog({ invoice, onCancelled }) {
  openModal({
    title: `Cancel Invoice ${invoice.invoice_number}`,
    small: true,
    renderBody: (body, close) => {
      const text = createElement(
        "p",
        "section-subtitle",
        `Cancel invoice "${invoice.invoice_number}"? Financial and audit history will be preserved.`
      );
      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");

      const form = createElement("form", "form-stack");
      const reasonField = createField({
        id: "void-reason",
        name: "reason",
        label: "Cancellation Reason (optional)",
        maxLength: 500,
        placeholder: "e.g. Revised order or customer requested cancellation",
      });
      form.appendChild(reasonField.wrapper);

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Keep Invoice");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);

      const confirmBtn = createElement("button", "btn btn-danger", "Cancel Invoice");
      confirmBtn.type = "submit";
      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      form.appendChild(actions);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        confirmBtn.disabled = true;
        confirmBtn.textContent = "Cancelling...";
        errorSlot.classList.add("is-hidden");
        try {
          const updated = await voidInvoice(
            invoice.id,
            reasonField.input.value.trim() || null
          );
          close();
          await onCancelled(updated);
        } catch (err) {
          confirmBtn.disabled = false;
          confirmBtn.textContent = "Cancel Invoice";
          errorSlot.textContent = err instanceof Error ? err.message : "Failed to cancel invoice.";
          errorSlot.classList.remove("is-hidden");
        }
      });

      body.appendChild(text);
      body.appendChild(errorSlot);
      body.appendChild(form);
    },
  });
}

export function createInvoicesController({
  getBusiness,
  onAuthExpired,
  onInvoicesChanged,
}) {
  const viewState = {
    mode: "list", // list | form | detail
    q: "",
    status: "all",
    page: 1,
    pageSize: 10,
    loading: false,
    error: null,
    listData: null,
    selectedInvoice: null,
    editingInvoice: null,
    customers: [],
    products: [],
  };

  async function loadList(container) {
    viewState.mode = "list";
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      viewState.listData = await fetchInvoices({
        q: viewState.q,
        status: viewState.status === "all" ? undefined : viewState.status,
        page: viewState.page,
        page_size: viewState.pageSize,
      });
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load invoices.";
    }
    render(container);
  }

  async function openForm(container, existingInvoice = null) {
    viewState.mode = "form";
    viewState.editingInvoice = existingInvoice;
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      const [custRes, prodRes] = await Promise.all([
        fetchCustomers({ is_active: true, page: 1, page_size: 100 }),
        fetchProducts({ is_active: true, page: 1, page_size: 100 }),
      ]);
      viewState.customers = custRes.items || [];
      viewState.products = prodRes.items || [];
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load customers and products.";
    }
    render(container);
  }

  async function openDetail(container, invoiceId) {
    viewState.mode = "detail";
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      viewState.selectedInvoice = await fetchInvoice(invoiceId);
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load invoice.";
    }
    render(container);
  }

  function renderListView(container) {
    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Invoices"));
    headingWrap.appendChild(
      createElement("p", "section-subtitle", "Create, edit, issue, preview, and download PDF invoices.")
    );
    const addBtn = createElement("button", "btn btn-primary", "+ New Invoice");
    addBtn.type = "button";
    addBtn.addEventListener("click", () => void openForm(container, null));
    header.appendChild(headingWrap);
    header.appendChild(addBtn);
    container.appendChild(header);

    const card = createElement("section", "card");
    const toolbar = createElement("div", "toolbar");
    const filters = createElement("div", "toolbar-filters");

    const searchInput = createElement("input", "form-input toolbar-search");
    searchInput.type = "search";
    searchInput.placeholder = "Search invoice # or customer...";
    searchInput.value = viewState.q;
    searchInput.setAttribute("aria-label", "Search invoices");

    const statusSelect = createElement("select", "form-input toolbar-select");
    statusSelect.setAttribute("aria-label", "Filter invoices by status");
    for (const [val, label] of [
      ["all", "All Statuses"],
      ["draft", "Draft"],
      ["issued", "Issued"],
      ["partially_paid", "Partially Paid"],
      ["paid", "Paid"],
      ["overdue", "Overdue"],
      ["void", "Cancelled / Void"],
    ]) {
      const opt = createElement("option", "", label);
      opt.value = val;
      if (viewState.status === val) opt.selected = true;
      statusSelect.appendChild(opt);
    }

    const searchBtn = createElement("button", "btn", "Search");
    searchBtn.type = "button";
    const applyFilter = () => {
      viewState.q = searchInput.value.trim();
      viewState.status = statusSelect.value;
      viewState.page = 1;
      void loadList(container);
    };
    searchBtn.addEventListener("click", applyFilter);
    statusSelect.addEventListener("change", applyFilter);
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        applyFilter();
      }
    });

    filters.appendChild(searchInput);
    filters.appendChild(statusSelect);
    filters.appendChild(searchBtn);
    toolbar.appendChild(filters);
    card.appendChild(toolbar);

    if (viewState.loading) {
      card.appendChild(createElement("p", "section-subtitle", "Loading invoices..."));
      container.appendChild(card);
      return;
    }

    if (viewState.error) {
      const alert = createElement("div", "alert alert-error", viewState.error);
      alert.setAttribute("role", "alert");
      card.appendChild(alert);
      container.appendChild(card);
      return;
    }

    const items = viewState.listData?.items || [];
    if (items.length === 0) {
      const empty = createElement("div", "empty-state");
      empty.appendChild(createElement("h3", "empty-state-title", "No invoices found"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          viewState.q || viewState.status !== "all"
            ? "No invoices match your search or status filter."
            : "Create your first invoice with server-validated GST totals and PDF export."
        )
      );
      const createBtn = createElement("button", "btn btn-primary", "Create Invoice");
      createBtn.type = "button";
      createBtn.addEventListener("click", () => void openForm(container, null));
      empty.appendChild(createBtn);
      card.appendChild(empty);
      container.appendChild(card);
      return;
    }

    const scroll = createElement("div", "table-scroll");
    const table = createElement("table", "data-table");
    const thead = createElement("thead");
    const headRow = createElement("tr");
    for (const [label, cls] of [
      ["Invoice #", ""],
      ["Customer", ""],
      ["Dates", ""],
      ["Status", ""],
      ["Total", "cell-numeric"],
      ["Balance Due", "cell-numeric"],
      ["", ""],
    ]) {
      headRow.appendChild(createElement("th", cls, label));
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = createElement("tbody");
    for (const inv of items) {
      const row = createElement("tr");

      const numCell = createElement("td");
      const viewLinkBtn = createElement("button", "btn btn-sm", inv.invoice_number);
      viewLinkBtn.type = "button";
      viewLinkBtn.addEventListener("click", () => void openDetail(container, inv.id));
      numCell.appendChild(viewLinkBtn);

      const custCell = createElement("td");
      custCell.appendChild(createElement("span", "cell-primary", inv.customer?.name || "—"));
      if (inv.customer?.company_name) {
        custCell.appendChild(createElement("span", "cell-secondary", inv.customer.company_name));
      }

      const dateCell = createElement("td");
      dateCell.appendChild(createElement("span", "", `Issued: ${inv.issue_date}`));
      dateCell.appendChild(createElement("span", "cell-secondary", `Due: ${inv.due_date}`));

      const statusCell = createElement("td");
      statusCell.appendChild(statusBadge(inv.effective_status));

      const totalCell = createElement(
        "td",
        "cell-numeric",
        formatCurrency(inv.total_amount, inv.currency_code)
      );
      const balCell = createElement(
        "td",
        "cell-numeric",
        formatCurrency(inv.balance_due, inv.currency_code)
      );

      const actionCell = createElement("td");
      const wrap = createElement("div", "table-actions");

      const previewBtn = createElement("button", "btn btn-sm", "View");
      previewBtn.type = "button";
      previewBtn.addEventListener("click", () => void openDetail(container, inv.id));
      wrap.appendChild(previewBtn);

      if (inv.is_editable) {
        const editBtn = createElement("button", "btn btn-sm", "Edit");
        editBtn.type = "button";
        editBtn.addEventListener("click", () => void openForm(container, inv));
        wrap.appendChild(editBtn);
      }

      const dupBtn = createElement("button", "btn btn-sm", "Duplicate");
      dupBtn.type = "button";
      dupBtn.addEventListener("click", async () => {
        dupBtn.disabled = true;
        try {
          const copy = await duplicateInvoice(inv.id);
          onInvoicesChanged();
          showToast(`Created duplicate draft ${copy.invoice_number}.`, "success");
          await openDetail(container, copy.id);
        } catch (err) {
          dupBtn.disabled = false;
          showToast(err instanceof Error ? err.message : "Failed to duplicate invoice.", "error");
        }
      });
      wrap.appendChild(dupBtn);

      const pdfLink = createElement("a", "btn btn-sm", "PDF");
      pdfLink.href = getInvoicePdfUrl(inv.id, "attachment");
      wrap.appendChild(pdfLink);

      if (inv.is_deletable) {
        const delBtn = createElement("button", "btn btn-sm btn-danger-outline", "Delete");
        delBtn.type = "button";
        delBtn.addEventListener("click", () => {
          openConfirmDialog({
            title: `Permanently Delete Invoice ${inv.invoice_number}`,
            message: `Are you sure you want to permanently delete ${inv.status === "void" ? "cancelled " : "draft "}invoice "${inv.invoice_number}" (${formatCurrency(inv.total_amount, inv.currency_code)}) from the database? Line items and cached PDFs will be removed and cannot be recovered.`,
            confirmLabel: "Delete Permanently",
            onConfirm: async () => {
              try {
                await deleteInvoice(inv.id);
                onInvoicesChanged();
                showToast(`Invoice ${inv.invoice_number} permanently deleted.`, "success");
                await loadList(container);
              } catch (err) {
                const msg = err instanceof Error ? err.message : "Failed to delete invoice.";
                showToast(msg, "error");
                throw err;
              }
            },
          });
        });
        wrap.appendChild(delBtn);
      } else if (inv.status !== "void" && Number(inv.amount_paid) === 0) {
        const cancelBtn = createElement("button", "btn btn-sm btn-danger-outline", "Cancel");
        cancelBtn.type = "button";
        cancelBtn.title = "Cancel (void) issued invoice while keeping accounting audit history";
        cancelBtn.addEventListener("click", () => {
          openCancelInvoiceDialog({
            invoice: inv,
            onCancelled: async () => {
              onInvoicesChanged();
              showToast(`Invoice ${inv.invoice_number} cancelled (void).`, "info");
              await loadList(container);
            },
          });
        });
        wrap.appendChild(cancelBtn);
      } else {
        const lockedDelBtn = createElement("button", "btn btn-sm btn-danger-outline", "Delete");
        lockedDelBtn.type = "button";
        lockedDelBtn.disabled = true;
        lockedDelBtn.title =
          inv.delete_block_reason ||
          "Invoices with recorded payments cannot be permanently deleted.";
        wrap.appendChild(lockedDelBtn);
      }

      actionCell.appendChild(wrap);

      row.appendChild(numCell);
      row.appendChild(custCell);
      row.appendChild(dateCell);
      row.appendChild(statusCell);
      row.appendChild(totalCell);
      row.appendChild(balCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    }

    table.appendChild(tbody);
    scroll.appendChild(table);
    card.appendChild(scroll);

    card.appendChild(
      renderPaginationBar({
        page: viewState.listData.page,
        totalPages: viewState.listData.total_pages,
        total: viewState.listData.total,
        onPageChange: (nextPage) => {
          viewState.page = nextPage;
          void loadList(container);
        },
      })
    );

    container.appendChild(card);
  }

  function renderFormView(container) {
    const existing = viewState.editingInvoice;
    const isEdit = Boolean(existing);
    const business = getBusiness();
    const currencyCode = existing?.currency_code || business?.currency_code || "USD";

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(
      createElement(
        "h2",
        "section-heading",
        isEdit ? `Edit Invoice ${existing.invoice_number}` : "Create Invoice"
      )
    );
    headingWrap.appendChild(
      createElement(
        "p",
        "section-subtitle",
        "Edit customer, dates, GST mode, HSN codes, items, and prices. Totals and modification history are saved on the server."
      )
    );
    const backBtn = createElement("button", "btn", "Back to Invoices");
    backBtn.type = "button";
    backBtn.addEventListener("click", () => void loadList(container));
    header.appendChild(headingWrap);
    header.appendChild(backBtn);
    container.appendChild(header);

    const card = createElement("section", "card");
    if (viewState.loading) {
      card.appendChild(createElement("p", "section-subtitle", "Loading customers and products..."));
      container.appendChild(card);
      return;
    }

    if (viewState.customers.length === 0) {
      const empty = createElement("div", "empty-state");
      empty.appendChild(createElement("h3", "empty-state-title", "Add a customer first"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          "Invoices require an active customer. Add one in the Customers section before creating an invoice."
        )
      );
      card.appendChild(empty);
      container.appendChild(card);
      return;
    }

    const errorSlot = createElement("div", "alert alert-error is-hidden");
    errorSlot.setAttribute("role", "alert");
    card.appendChild(errorSlot);

    const form = createElement("form", "form-stack");
    const topGrid = createElement("div", "form-grid");

    // Customer select
    const custWrap = createElement("div", "form-field");
    const custLabel = createElement("label", "form-label", "Customer *");
    custLabel.setAttribute("for", "inv-customer");
    const custSelect = createElement("select", "form-input");
    custSelect.id = "inv-customer";
    custSelect.required = true;
    for (const c of viewState.customers) {
      const optLabel = c.company_name ? `${c.name} (${c.company_name})` : c.name;
      const opt = createElement("option", "", optLabel);
      opt.value = String(c.id);
      if (existing && existing.customer_id === c.id) opt.selected = true;
      custSelect.appendChild(opt);
    }
    custWrap.appendChild(custLabel);
    custWrap.appendChild(custSelect);

    // GST Mode select
    const gstWrap = createElement("div", "form-field");
    const gstLabel = createElement("label", "form-label", "GST Calculation Mode *");
    gstLabel.setAttribute("for", "inv-gst-mode");
    const gstSelect = createElement("select", "form-input");
    gstSelect.id = "inv-gst-mode";
    for (const [val, label] of [
      ["auto", "Auto (CGST+SGST if same state, else IGST)"],
      ["cgst_sgst", "CGST + SGST (Intra-State)"],
      ["igst", "IGST (Inter-State)"],
    ]) {
      const opt = createElement("option", "", label);
      opt.value = val;
      if ((existing?.gst_mode || "auto") === val) opt.selected = true;
      gstSelect.appendChild(opt);
    }
    gstWrap.appendChild(gstLabel);
    gstWrap.appendChild(gstSelect);

    topGrid.appendChild(custWrap);
    topGrid.appendChild(gstWrap);

    const issueDateField = createField({
      id: "inv-issue-date",
      name: "issue_date",
      label: "Issue Date *",
      type: "date",
      required: true,
      value: existing?.issue_date || todayIso(),
    });
    const dueDateField = createField({
      id: "inv-due-date",
      name: "due_date",
      label: "Due Date *",
      type: "date",
      required: true,
      value: existing?.due_date || addDaysIso(14),
    });
    topGrid.appendChild(issueDateField.wrapper);
    topGrid.appendChild(dueDateField.wrapper);
    form.appendChild(topGrid);

    // Line items state
    const lines = (
      existing?.items?.length
        ? existing.items.map((it) => ({
            product_id: it.product_id ? String(it.product_id) : "",
            item_name: it.item_name,
            hsn_code: it.hsn_code || "",
            description: it.description || "",
            unit: it.unit || "",
            quantity: String(it.quantity),
            unit_price: String(it.unit_price),
            discount_percent: String(it.discount_percent),
            tax_rate: String(it.tax_rate),
            tax_label: it.tax_label || "",
          }))
        : [
            {
              product_id: "",
              item_name: "",
              hsn_code: "",
              description: "",
              unit: "",
              quantity: "1.00",
              unit_price: "0.00",
              discount_percent: "0.00",
              tax_rate: "0.00",
              tax_label: "",
            },
          ]
    );

    const itemsHeader = createElement("div", "card-header");
    itemsHeader.appendChild(createElement("h3", "card-title", "Line Items"));
    const addLineBtn = createElement("button", "btn btn-sm", "+ Add Line Item");
    addLineBtn.type = "button";
    itemsHeader.appendChild(addLineBtn);
    form.appendChild(itemsHeader);

    const linesContainer = createElement("div", "line-items-wrap");
    form.appendChild(linesContainer);

    const totalsBox = createElement("div", "totals-summary");
    form.appendChild(totalsBox);

    function currentGstType() {
      const selectedCust = viewState.customers.find(
        (c) => String(c.id) === custSelect.value
      );
      return resolvePreviewGstType(gstSelect.value, business, selectedCust);
    }

    function renderTotalsPreview() {
      totalsBox.replaceChildren();
      const gstType = currentGstType();
      let sub = 0;
      let disc = 0;
      let cgst = 0;
      let sgst = 0;
      let igst = 0;
      let tax = 0;
      for (const line of lines) {
        const calc = computePreviewLine(line, gstType);
        sub += calc.subtotal;
        disc += calc.discount;
        cgst += calc.cgst;
        sgst += calc.sgst;
        igst += calc.igst;
        tax += calc.tax;
      }
      const grand = roundMoney(sub - disc + tax);
      const rows = [
        ["Subtotal", formatCurrency(sub, currencyCode), false],
        ["Discount", `-${formatCurrency(disc, currencyCode)}`, false],
      ];
      if (gstType === "igst") {
        rows.push(["IGST", formatCurrency(igst, currencyCode), false]);
      } else {
        rows.push(["CGST", formatCurrency(cgst, currencyCode), false]);
        rows.push(["SGST", formatCurrency(sgst, currencyCode), false]);
      }
      rows.push(["Total Tax", formatCurrency(tax, currencyCode), false]);
      rows.push(["Estimated Total", formatCurrency(grand, currencyCode), true]);

      for (const [label, val, isGrand] of rows) {
        const r = createElement("div", isGrand ? "totals-row totals-row-grand" : "totals-row");
        r.appendChild(createElement("span", "", label));
        r.appendChild(createElement("span", "", val));
        totalsBox.appendChild(r);
      }
    }

    function renderLines() {
      linesContainer.replaceChildren();
      const gstType = currentGstType();

      lines.forEach((line, idx) => {
        const cardRow = createElement("div", "line-item-card");
        const topRow = createElement("div", "line-item-top");
        const bottomRow = createElement("div", "line-item-bottom");

        // Product selector
        const prodWrap = createElement("div", "form-field");
        const prodLabel = createElement("label", "form-label", "Catalog Item");
        const prodSelect = createElement("select", "form-input");
        prodSelect.id = `line-product-${idx}`;
        prodLabel.setAttribute("for", prodSelect.id);
        const customOpt = createElement("option", "", "Custom item...");
        customOpt.value = "";
        prodSelect.appendChild(customOpt);
        for (const p of viewState.products) {
          const hsnTag = p.hsn_code ? ` • HSN ${p.hsn_code}` : "";
          const opt = createElement(
            "option",
            "",
            `${p.name}${hsnTag} (${formatCurrency(p.unit_price, currencyCode)})`
          );
          opt.value = String(p.id);
          if (line.product_id === String(p.id)) opt.selected = true;
          prodSelect.appendChild(opt);
        }
        prodWrap.appendChild(prodLabel);
        prodWrap.appendChild(prodSelect);

        const nameField = createField({
          id: `line-name-${idx}`,
          name: "item_name",
          label: "Item Name *",
          required: true,
          maxLength: 160,
          value: line.item_name,
        });
        const hsnField = createField({
          id: `line-hsn-${idx}`,
          name: "hsn_code",
          label: "HSN Code",
          maxLength: 16,
          placeholder: "4-8 digits",
          value: line.hsn_code,
        });

        const removeBtn = createElement("button", "btn btn-sm btn-danger-outline", "Remove");
        removeBtn.type = "button";
        removeBtn.disabled = lines.length <= 1;
        removeBtn.addEventListener("click", () => {
          lines.splice(idx, 1);
          renderLines();
          renderTotalsPreview();
        });

        topRow.appendChild(prodWrap);
        topRow.appendChild(nameField.wrapper);
        topRow.appendChild(hsnField.wrapper);
        topRow.appendChild(removeBtn);

        const qtyField = createField({
          id: `line-qty-${idx}`,
          name: "quantity",
          label: "Qty *",
          type: "number",
          required: true,
          min: 0.01,
          step: "0.01",
          value: line.quantity,
        });
        const priceField = createField({
          id: `line-price-${idx}`,
          name: "unit_price",
          label: "Selling Price *",
          type: "number",
          required: true,
          min: 0,
          step: "0.01",
          value: line.unit_price,
        });
        const discField = createField({
          id: `line-disc-${idx}`,
          name: "discount_percent",
          label: "Disc %",
          type: "number",
          min: 0,
          max: 100,
          step: "0.01",
          value: line.discount_percent,
        });
        const taxField = createField({
          id: `line-tax-${idx}`,
          name: "tax_rate",
          label: "GST %",
          type: "number",
          min: 0,
          max: 100,
          step: "0.01",
          value: line.tax_rate,
        });

        const totalBox = createElement("div", "line-item-total-box");
        totalBox.appendChild(createElement("span", "form-label", "Line Total"));
        const totalVal = createElement(
          "span",
          "line-item-total-val",
          formatCurrency(computePreviewLine(line, gstType).total, currencyCode)
        );
        totalBox.appendChild(totalVal);

        bottomRow.appendChild(qtyField.wrapper);
        bottomRow.appendChild(priceField.wrapper);
        bottomRow.appendChild(discField.wrapper);
        bottomRow.appendChild(taxField.wrapper);
        bottomRow.appendChild(totalBox);

        const syncLine = () => {
          line.item_name = nameField.input.value;
          line.hsn_code = hsnField.input.value;
          line.quantity = qtyField.input.value;
          line.unit_price = priceField.input.value;
          line.discount_percent = discField.input.value;
          line.tax_rate = taxField.input.value;
          totalVal.textContent = formatCurrency(
            computePreviewLine(line, currentGstType()).total,
            currencyCode
          );
          renderTotalsPreview();
        };

        prodSelect.addEventListener("change", () => {
          line.product_id = prodSelect.value;
          const selected = viewState.products.find((p) => String(p.id) === prodSelect.value);
          if (selected) {
            line.item_name = selected.name;
            line.hsn_code = selected.hsn_code || "";
            line.description = selected.description || "";
            line.unit = selected.unit || "";
            line.unit_price = String(selected.unit_price);
            line.tax_rate = String(selected.tax_rate);
            line.tax_label = selected.tax_label || "";
            nameField.input.value = line.item_name;
            hsnField.input.value = line.hsn_code;
            priceField.input.value = line.unit_price;
            taxField.input.value = line.tax_rate;
            syncLine();
          }
        });

        nameField.input.addEventListener("input", syncLine);
        hsnField.input.addEventListener("input", syncLine);
        qtyField.input.addEventListener("input", syncLine);
        priceField.input.addEventListener("input", syncLine);
        discField.input.addEventListener("input", syncLine);
        taxField.input.addEventListener("input", syncLine);

        cardRow.appendChild(topRow);
        cardRow.appendChild(bottomRow);
        linesContainer.appendChild(cardRow);
      });
    }

    custSelect.addEventListener("change", () => {
      renderLines();
      renderTotalsPreview();
    });
    gstSelect.addEventListener("change", () => {
      renderLines();
      renderTotalsPreview();
    });

    addLineBtn.addEventListener("click", () => {
      lines.push({
        product_id: "",
        item_name: "",
        hsn_code: "",
        description: "",
        unit: "",
        quantity: "1.00",
        unit_price: "0.00",
        discount_percent: "0.00",
        tax_rate: "0.00",
        tax_label: "",
      });
      renderLines();
      renderTotalsPreview();
    });

    renderLines();
    renderTotalsPreview();

    const extraGrid = createElement("div", "form-grid");
    const notesField = createField({
      id: "inv-notes",
      name: "notes",
      label: "Notes",
      maxLength: 3000,
      value: existing?.notes || "",
    });
    const termsField = createField({
      id: "inv-terms",
      name: "terms",
      label: "Payment Terms",
      maxLength: 3000,
      placeholder: "Due within 14 days",
      value: existing?.terms || "",
    });
    extraGrid.appendChild(notesField.wrapper);
    extraGrid.appendChild(termsField.wrapper);
    form.appendChild(extraGrid);

    const actions = createElement("div", "form-actions");
    const cancelBtn = createElement("button", "btn", "Cancel");
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", () => void loadList(container));
    actions.appendChild(cancelBtn);

    let submitMode = "draft";
    const saveDraftBtn = createElement(
      "button",
      isEdit ? "btn btn-primary" : "btn",
      isEdit ? "Save Changes" : "Save as Draft"
    );
    saveDraftBtn.type = "submit";
    saveDraftBtn.addEventListener("click", () => {
      submitMode = "draft";
    });
    actions.appendChild(saveDraftBtn);

    let saveIssueBtn = null;
    if (!isEdit) {
      saveIssueBtn = createElement("button", "btn btn-primary", "Save & Issue");
      saveIssueBtn.type = "submit";
      saveIssueBtn.addEventListener("click", () => {
        submitMode = "issue";
      });
      actions.appendChild(saveIssueBtn);
    }

    form.appendChild(actions);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      saveDraftBtn.disabled = true;
      if (saveIssueBtn) saveIssueBtn.disabled = true;
      errorSlot.classList.add("is-hidden");

      const payload = {
        customer_id: Number.parseInt(custSelect.value, 10),
        issue_date: issueDateField.input.value,
        due_date: dueDateField.input.value,
        gst_mode: gstSelect.value,
        notes: notesField.input.value.trim() || null,
        terms: termsField.input.value.trim() || null,
        items: lines.map((line) => ({
          product_id: line.product_id ? Number.parseInt(line.product_id, 10) : null,
          item_name: line.item_name.trim(),
          hsn_code: line.hsn_code?.trim() || null,
          description: line.description?.trim() || null,
          unit: line.unit?.trim() || null,
          quantity: line.quantity || "1.00",
          unit_price: line.unit_price || "0.00",
          discount_percent: line.discount_percent || "0.00",
          tax_rate: line.tax_rate || "0.00",
          tax_label: line.tax_label?.trim() || null,
        })),
      };

      try {
        const saved = isEdit
          ? await updateInvoice(existing.id, payload)
          : await createInvoice({
              ...payload,
              issue_immediately: submitMode === "issue",
            });
        onInvoicesChanged();
        await openDetail(container, saved.id);
      } catch (err) {
        saveDraftBtn.disabled = false;
        if (saveIssueBtn) saveIssueBtn.disabled = false;
        errorSlot.textContent = err instanceof Error ? err.message : "Failed to save invoice.";
        errorSlot.classList.remove("is-hidden");
      }
    });

    card.appendChild(form);
    container.appendChild(card);
  }

  function renderDetailView(container) {
    const inv = viewState.selectedInvoice;
    const business = getBusiness();

    const header = createElement("div", "section-header no-print");
    const headingWrap = createElement("div");
    headingWrap.appendChild(
      createElement("h2", "section-heading", inv ? `Invoice ${inv.invoice_number}` : "Invoice Detail")
    );
    header.appendChild(headingWrap);

    const btnBar = createElement("div", "topbar-actions");
    const backBtn = createElement("button", "btn", "Back to Invoices");
    backBtn.type = "button";
    backBtn.addEventListener("click", () => void loadList(container));
    btnBar.appendChild(backBtn);

    if (inv && !viewState.loading) {
      if (inv.is_editable) {
        const editBtn = createElement("button", "btn", "Edit Invoice");
        editBtn.type = "button";
        editBtn.addEventListener("click", () => void openForm(container, inv));
        btnBar.appendChild(editBtn);
      }

      const dupBtn = createElement("button", "btn", "Duplicate");
      dupBtn.type = "button";
      dupBtn.addEventListener("click", async () => {
        dupBtn.disabled = true;
        try {
          const copy = await duplicateInvoice(inv.id);
          onInvoicesChanged();
          showToast(`Created duplicate draft ${copy.invoice_number}.`, "success");
          await openDetail(container, copy.id);
        } catch (err) {
          dupBtn.disabled = false;
          showToast(err instanceof Error ? err.message : "Failed to duplicate invoice.", "error");
        }
      });
      btnBar.appendChild(dupBtn);

      if (inv.status === "draft") {
        const issueBtn = createElement("button", "btn btn-primary", "Issue Invoice");
        issueBtn.type = "button";
        issueBtn.addEventListener("click", async () => {
          issueBtn.disabled = true;
          try {
            viewState.selectedInvoice = await issueInvoice(inv.id);
            onInvoicesChanged();
            showToast(`Invoice ${inv.invoice_number} issued.`, "success");
            render(container);
          } catch (err) {
            issueBtn.disabled = false;
            const msg = err instanceof Error ? err.message : "Failed to issue invoice.";
            viewState.error = msg;
            showToast(msg, "error");
            render(container);
          }
        });
        btnBar.appendChild(issueBtn);
      } else if (inv.status !== "void") {
        if (Number(inv.balance_due) > 0) {
          const payBtn = createElement("button", "btn btn-primary", "Record Payment");
          payBtn.type = "button";
          payBtn.addEventListener("click", () => {
            void openRecordPaymentModal({
              preselectedInvoice: inv,
              onSaved: async () => {
                onInvoicesChanged();
                await openDetail(container, inv.id);
              },
            });
          });
          btnBar.appendChild(payBtn);
        }
        if (Number(inv.amount_paid) === 0) {
          const voidBtn = createElement("button", "btn btn-danger-outline", "Cancel Invoice");
          voidBtn.type = "button";
          voidBtn.addEventListener("click", () => {
            openCancelInvoiceDialog({
              invoice: inv,
              onCancelled: async (updated) => {
                viewState.selectedInvoice = updated;
                onInvoicesChanged();
                showToast(`Invoice ${inv.invoice_number} cancelled (void).`, "info");
                render(container);
              },
            });
          });
          btnBar.appendChild(voidBtn);
        }
      }

      if (inv.is_deletable) {
        const delBtn = createElement("button", "btn btn-danger", "Delete Permanently");
        delBtn.type = "button";
        delBtn.addEventListener("click", () => {
          openConfirmDialog({
            title: `Permanently Delete Invoice ${inv.invoice_number}`,
            message: `Permanently delete ${inv.status === "void" ? "cancelled " : "draft "}invoice "${inv.invoice_number}" (${formatCurrency(inv.total_amount, inv.currency_code)}) from the database? Line items and cached PDFs will be removed permanently.`,
            confirmLabel: "Delete Permanently",
            onConfirm: async () => {
              try {
                await deleteInvoice(inv.id);
                onInvoicesChanged();
                showToast(`Invoice ${inv.invoice_number} permanently deleted.`, "success");
                await loadList(container);
              } catch (err) {
                const msg = err instanceof Error ? err.message : "Failed to delete invoice.";
                showToast(msg, "error");
                throw err;
              }
            },
          });
        });
        btnBar.appendChild(delBtn);
      }

      const printBtn = createElement("button", "btn", "Print");
      printBtn.type = "button";
      printBtn.addEventListener("click", () => window.print());
      btnBar.appendChild(printBtn);

      const pdfBtn = createElement("a", "btn btn-primary", "Download PDF");
      pdfBtn.href = `${getInvoicePdfUrl(inv.id, "attachment")}&v=${encodeURIComponent(inv.updated_at)}`;
      btnBar.appendChild(pdfBtn);
    }

    header.appendChild(btnBar);
    container.appendChild(header);

    if (viewState.loading) {
      const card = createElement("section", "card");
      card.appendChild(createElement("p", "section-subtitle", "Loading invoice details..."));
      container.appendChild(card);
      return;
    }

    if (viewState.error) {
      const alert = createElement("div", "alert alert-error", viewState.error);
      alert.setAttribute("role", "alert");
      container.appendChild(alert);
      if (!inv) return;
    }

    const sheet = createElement("article", "invoice-sheet");
    applyInvoiceThemeVariables(sheet, inv.theme || extractThemeFromBusiness(business));

    // Sheet Header
    const sheetHeader = createElement("div", "invoice-sheet-header");
    const bizWrap = createElement("div", "invoice-sheet-brand-wrap");
    const logoMeta = inv.logo;
    if (logoMeta?.has_logo ?? business?.has_logo) {
      const logoImg = document.createElement("img");
      logoImg.className = "invoice-sheet-logo";
      logoImg.alt = "Business logo";
      logoImg.src = `${getBusinessLogoUrl()}?v=${encodeURIComponent(
        logoMeta?.logo_updated_at || business?.logo_updated_at || inv.updated_at
      )}`;
      logoImg.addEventListener("error", () => logoImg.remove());
      bizWrap.appendChild(logoImg);
    }

    const bizCol = createElement("div");
    bizCol.appendChild(createElement("h3", "invoice-sheet-brand", business?.name || "Business"));
    const bizLines = [
      business?.legal_name,
      business?.address_line1,
      business?.address_line2,
      [business?.city, business?.state, business?.postal_code].filter(Boolean).join(", "),
      business?.country,
      business?.email ? `Email: ${business.email}` : null,
      business?.phone ? `Phone: ${business.phone}` : null,
      business?.tax_id ? `Tax ID: ${business.tax_id}` : null,
    ].filter(Boolean);
    bizCol.appendChild(createElement("p", "invoice-header-subtext", bizLines.join("\n")));
    bizWrap.appendChild(bizCol);

    const metaCol = createElement("div");
    metaCol.appendChild(createElement("h3", "invoice-sheet-title", "INVOICE"));
    const metaList = createElement("div", "invoice-sheet-meta");
    const metaEntries = [
      ["Invoice #", inv.invoice_number],
      ["Issue Date", inv.issue_date],
      ["Due Date", inv.due_date],
      ["GST Mode", inv.gst_type === "igst" ? "IGST" : "CGST + SGST"],
      ["Currency", inv.currency_code],
    ];
    for (const [k, v] of metaEntries) {
      const p = createElement("div");
      p.appendChild(createElement("span", "", `${k}: `));
      p.appendChild(createElement("strong", "", String(v)));
      metaList.appendChild(p);
    }
    const statusRow = createElement("div");
    statusRow.appendChild(statusBadge(inv.effective_status));
    metaList.appendChild(statusRow);
    metaCol.appendChild(metaList);

    sheetHeader.appendChild(bizWrap);
    sheetHeader.appendChild(metaCol);
    sheet.appendChild(sheetHeader);

    if (inv.status === "void" && inv.cancellation_reason) {
      const cancelNote = createElement(
        "div",
        "alert alert-error",
        `Cancelled: ${inv.cancellation_reason}`
      );
      sheet.appendChild(cancelNote);
    }

    // Bill To
    const parties = createElement("div", "invoice-sheet-parties");
    const billTo = createElement("div");
    billTo.appendChild(createElement("p", "invoice-party-label", "Bill To"));
    const c = inv.customer || {};
    const custLines = [
      c.name,
      c.company_name,
      c.address_line1,
      c.address_line2,
      [c.city, c.state, c.postal_code].filter(Boolean).join(", "),
      c.country,
      c.email ? `Email: ${c.email}` : null,
      c.phone ? `Phone: ${c.phone}` : null,
      c.tax_id ? `Tax ID: ${c.tax_id}` : null,
    ].filter(Boolean);
    billTo.appendChild(createElement("p", "invoice-party-text", custLines.join("\n")));
    parties.appendChild(billTo);
    sheet.appendChild(parties);

    // Items Table
    const scroll = createElement("div", "table-scroll");
    const table = createElement("table", "data-table");
    const thead = createElement("thead");
    const headRow = createElement("tr");
    for (const [label, cls] of [
      ["Item", ""],
      ["HSN", ""],
      ["Qty", "cell-numeric"],
      ["Unit Price", "cell-numeric"],
      ["Discount", "cell-numeric"],
      ["GST", "cell-numeric"],
      ["Line Total", "cell-numeric"],
    ]) {
      headRow.appendChild(createElement("th", cls, label));
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = createElement("tbody");
    for (const item of inv.items || []) {
      const row = createElement("tr");
      const nameTd = createElement("td");
      nameTd.appendChild(
        createElement(
          "span",
          "cell-primary",
          item.unit ? `${item.item_name} (${item.unit})` : item.item_name
        )
      );
      if (item.description) {
        nameTd.appendChild(createElement("span", "cell-secondary", item.description));
      }

      row.appendChild(nameTd);
      row.appendChild(createElement("td", "", item.hsn_code || "—"));
      row.appendChild(createElement("td", "cell-numeric", Number(item.quantity).toFixed(2)));
      row.appendChild(
        createElement("td", "cell-numeric", formatCurrency(item.unit_price, inv.currency_code))
      );
      row.appendChild(
        createElement(
          "td",
          "cell-numeric",
          `${Number(item.discount_percent).toFixed(2)}% (${formatCurrency(item.line_discount, inv.currency_code)})`
        )
      );
      row.appendChild(
        createElement(
          "td",
          "cell-numeric",
          `${Number(item.tax_rate).toFixed(2)}% (${formatCurrency(item.line_tax, inv.currency_code)})`
        )
      );
      row.appendChild(
        createElement("td", "cell-numeric", formatCurrency(item.line_total, inv.currency_code))
      );
      tbody.appendChild(row);
    }
    table.appendChild(tbody);
    scroll.appendChild(table);
    sheet.appendChild(scroll);

    // Totals breakdown
    const totalsBox = createElement("div", "totals-summary");
    const summaryRows = [
      ["Subtotal", formatCurrency(inv.subtotal_amount, inv.currency_code), false],
      ["Discount", `-${formatCurrency(inv.discount_amount, inv.currency_code)}`, false],
    ];
    if (inv.gst_type === "igst") {
      summaryRows.push(["IGST", formatCurrency(inv.igst_amount, inv.currency_code), false]);
    } else {
      summaryRows.push(["CGST", formatCurrency(inv.cgst_amount, inv.currency_code), false]);
      summaryRows.push(["SGST", formatCurrency(inv.sgst_amount, inv.currency_code), false]);
    }
    summaryRows.push(
      ["Total Tax", formatCurrency(inv.tax_amount, inv.currency_code), false],
      ["Grand Total", formatCurrency(inv.total_amount, inv.currency_code), true],
      ["Amount Paid", formatCurrency(inv.amount_paid, inv.currency_code), false],
      ["Balance Due", formatCurrency(inv.balance_due, inv.currency_code), true]
    );

    for (const [label, val, isGrand] of summaryRows) {
      const r = createElement("div", isGrand ? "totals-row totals-row-grand" : "totals-row");
      r.appendChild(createElement("span", "", label));
      r.appendChild(createElement("span", "", val));
      totalsBox.appendChild(r);
    }
    sheet.appendChild(totalsBox);

    // Bank Details & Amount-Specific Payment QR Code
    const bank = inv.bank_details;
    const bankLines = bank
      ? [
          bank.bank_account_holder ? `Account Holder: ${bank.bank_account_holder}` : null,
          bank.bank_name ? `Bank Name: ${bank.bank_name}` : null,
          bank.bank_account_number ? `Account Number: ${bank.bank_account_number}` : null,
          bank.bank_ifsc_code ? `IFSC Code: ${bank.bank_ifsc_code}` : null,
          bank.bank_branch ? `Branch: ${bank.bank_branch}` : null,
          bank.upi_id ? `UPI ID: ${bank.upi_id}` : null,
        ].filter(Boolean)
      : [];

    if (bankLines.length > 0 || inv.payment_qr_available) {
      const bankQr = createElement("div", "bank-qr-section");
      if (bankLines.length > 0) {
        const bankCol = createElement("div");
        bankCol.appendChild(createElement("p", "invoice-party-label", "Bank & Payment Details"));
        bankCol.appendChild(createElement("p", "invoice-party-text", bankLines.join("\n")));
        bankQr.appendChild(bankCol);
      }
      if (inv.payment_qr_available) {
        const qrCard = createElement("div", "qr-card");
        const img = document.createElement("img");
        img.className = "qr-image";
        img.src = `${getInvoiceQrUrl(inv.id)}?v=${encodeURIComponent(inv.updated_at)}`;
        img.alt = `UPI Payment QR code for ${inv.invoice_number}`;
        qrCard.appendChild(img);
        qrCard.appendChild(
          createElement(
            "span",
            "qr-caption",
            `Scan & Pay ${formatCurrency(inv.balance_due, inv.currency_code)}`
          )
        );
        qrCard.appendChild(createElement("span", "qr-subcaption", `Ref: ${inv.invoice_number}`));
        bankQr.appendChild(qrCard);
      }
      sheet.appendChild(bankQr);
    }

    if (inv.notes || inv.terms) {
      const notesGrid = createElement("div", "invoice-sheet-notes");
      if (inv.notes) {
        const nCol = createElement("div");
        nCol.appendChild(createElement("p", "invoice-party-label", "Notes"));
        nCol.appendChild(createElement("p", "invoice-party-text", inv.notes));
        notesGrid.appendChild(nCol);
      }
      if (inv.terms) {
        const tCol = createElement("div");
        tCol.appendChild(createElement("p", "invoice-party-label", "Payment Terms"));
        tCol.appendChild(createElement("p", "invoice-party-text", inv.terms));
        notesGrid.appendChild(tCol);
      }
      sheet.appendChild(notesGrid);
    }

    // Authorized Visual Signature Section
    const sig = inv.signature;
    if (sig?.has_signature && sig?.signature_enabled) {
      const sigRow = createElement("div", "invoice-signature-row");
      sigRow.dataset.placement = sig.signature_placement || "bottom_right";

      const sigBox = createElement("div", "invoice-signature-box");
      sigBox.appendChild(
        createElement("span", "cell-secondary", `For ${business?.name || "Business"}`)
      );

      const sigImg = document.createElement("img");
      sigImg.className = "invoice-signature-img";
      sigImg.alt = "Authorized Signatory";
      sigImg.src = `${getBusinessSignatureUrl()}?v=${encodeURIComponent(sig.signature_updated_at || inv.updated_at)}`;
      sigBox.appendChild(sigImg);

      sigBox.appendChild(createElement("strong", "", "Authorized Signatory"));
      sigRow.appendChild(sigBox);
      sheet.appendChild(sigRow);
    }

    container.appendChild(sheet);

    // Modification History card (excluded from print)
    const historyCard = createElement("section", "card no-print");
    const historyHeader = createElement("div", "card-header");
    historyHeader.appendChild(createElement("h3", "card-title", "Modification History"));
    historyCard.appendChild(historyHeader);

    const mods = inv.modifications || [];
    if (mods.length === 0) {
      historyCard.appendChild(
        createElement("p", "section-subtitle", "No modifications recorded yet.")
      );
    } else {
      const list = createElement("div", "history-list");
      for (const mod of mods) {
        const item = createElement("div", "history-item");
        const head = createElement("div", "history-item-head");
        head.appendChild(createElement("strong", "", mod.summary));
        head.appendChild(
          createElement("span", "history-item-meta", new Date(mod.created_at).toLocaleString())
        );
        item.appendChild(head);
        item.appendChild(
          createElement(
            "div",
            "history-item-meta",
            `By ${mod.modified_by_name} (${mod.modified_by_email}) • Action: ${mod.action}`
          )
        );
        if (mod.changes_json) {
          item.appendChild(
            createElement(
              "div",
              "cell-secondary",
              `Changes: ${JSON.stringify(mod.changes_json)}`
            )
          );
        }
        list.appendChild(item);
      }
      historyCard.appendChild(list);
    }
    container.appendChild(historyCard);
  }

  function render(container) {
    container.replaceChildren();
    if (viewState.mode === "form") {
      renderFormView(container);
    } else if (viewState.mode === "detail") {
      renderDetailView(container);
    } else {
      renderListView(container);
    }
  }

  return {
    mount: (container) => loadList(container),
    openCreate: (container) => openForm(container, null),
    openDetail: (container, invoiceId) => openDetail(container, invoiceId),
  };
}
