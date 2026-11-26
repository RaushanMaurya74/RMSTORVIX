/**
 * Payments management view and shared Record Payment modal.
 */

import {
  deletePayment,
  fetchInvoices,
  fetchPayments,
  recordPayment,
} from "/js/api.js";
import {
  createElement,
  createField,
  formatCurrency,
  renderPaginationBar,
} from "/js/dom.js";
import { openConfirmDialog, openModal } from "/js/modal.js";

const PAYMENT_METHODS = [
  ["bank_transfer", "Bank Transfer"],
  ["cash", "Cash"],
  ["card", "Card"],
  ["upi", "UPI"],
  ["cheque", "Cheque"],
  ["other", "Other"],
];

function formatMethodLabel(method) {
  const match = PAYMENT_METHODS.find(([k]) => k === method);
  return match ? match[1] : method;
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export async function openRecordPaymentModal({ preselectedInvoice = null, onSaved }) {
  let openInvoices = [];
  if (preselectedInvoice) {
    openInvoices = [preselectedInvoice];
  } else {
    const [issuedRes, partialRes, overdueRes] = await Promise.all([
      fetchInvoices({ status: "issued", page: 1, page_size: 100 }),
      fetchInvoices({ status: "partially_paid", page: 1, page_size: 100 }),
      fetchInvoices({ status: "overdue", page: 1, page_size: 100 }),
    ]);
    const map = new Map();
    for (const inv of [
      ...(issuedRes.items || []),
      ...(partialRes.items || []),
      ...(overdueRes.items || []),
    ]) {
      if (Number(inv.balance_due) > 0) {
        map.set(inv.id, inv);
      }
    }
    openInvoices = Array.from(map.values());
  }

  openModal({
    title: "Record Payment",
    renderBody: (body, close) => {
      if (openInvoices.length === 0) {
        body.appendChild(
          createElement(
            "p",
            "section-subtitle",
            "There are no issued invoices with an open balance due. Issue a draft invoice first."
          )
        );
        const actions = createElement("div", "form-actions");
        const okBtn = createElement("button", "btn", "Close");
        okBtn.type = "button";
        okBtn.addEventListener("click", close);
        actions.appendChild(okBtn);
        body.appendChild(actions);
        return;
      }

      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");
      body.appendChild(errorSlot);

      const form = createElement("form", "form-stack");
      const grid = createElement("div", "form-grid");

      const invWrap = createElement("div", "form-field form-field-full");
      const invLabel = createElement("label", "form-label", "Invoice *");
      invLabel.setAttribute("for", "pay-invoice");
      const invSelect = createElement("select", "form-input");
      invSelect.id = "pay-invoice";
      invSelect.required = true;
      for (const inv of openInvoices) {
        const opt = createElement(
          "option",
          "",
          `${inv.invoice_number} — ${inv.customer?.name || "Customer"} (Due: ${formatCurrency(inv.balance_due, inv.currency_code)})`
        );
        opt.value = String(inv.id);
        invSelect.appendChild(opt);
      }
      if (preselectedInvoice) {
        invSelect.disabled = true;
      }
      invWrap.appendChild(invLabel);
      invWrap.appendChild(invSelect);
      grid.appendChild(invWrap);

      const firstInv = openInvoices[0];
      const amountField = createField({
        id: "pay-amount",
        name: "amount",
        label: `Amount (${firstInv.currency_code}) *`,
        type: "number",
        required: true,
        min: 0.01,
        step: "0.01",
        value: String(firstInv.balance_due),
      });
      const dateField = createField({
        id: "pay-date",
        name: "payment_date",
        label: "Payment Date *",
        type: "date",
        required: true,
        value: todayIso(),
      });

      const methodWrap = createElement("div", "form-field");
      const methodLabel = createElement("label", "form-label", "Payment Method *");
      methodLabel.setAttribute("for", "pay-method");
      const methodSelect = createElement("select", "form-input");
      methodSelect.id = "pay-method";
      for (const [val, label] of PAYMENT_METHODS) {
        const opt = createElement("option", "", label);
        opt.value = val;
        methodSelect.appendChild(opt);
      }
      methodWrap.appendChild(methodLabel);
      methodWrap.appendChild(methodSelect);

      const refField = createField({
        id: "pay-ref",
        name: "reference",
        label: "Reference / Transaction ID",
        maxLength: 120,
        placeholder: "TXN-10492",
      });
      const notesField = createField({
        id: "pay-notes",
        name: "notes",
        label: "Notes",
        maxLength: 2000,
        fullWidth: true,
      });

      invSelect.addEventListener("change", () => {
        const chosen = openInvoices.find((i) => String(i.id) === invSelect.value);
        if (chosen) {
          amountField.input.value = String(chosen.balance_due);
        }
      });

      grid.appendChild(amountField.wrapper);
      grid.appendChild(dateField.wrapper);
      grid.appendChild(methodWrap);
      grid.appendChild(refField.wrapper);
      grid.appendChild(notesField.wrapper);
      form.appendChild(grid);

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Cancel");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);

      const submitBtn = createElement("button", "btn btn-primary", "Record Payment");
      submitBtn.type = "submit";
      actions.appendChild(cancelBtn);
      actions.appendChild(submitBtn);
      form.appendChild(actions);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        submitBtn.disabled = true;
        submitBtn.textContent = "Recording...";
        errorSlot.classList.add("is-hidden");

        try {
          await recordPayment({
            invoice_id: Number.parseInt(invSelect.value, 10),
            amount: amountField.input.value,
            payment_date: dateField.input.value,
            payment_method: methodSelect.value,
            reference: refField.input.value.trim() || null,
            notes: notesField.input.value.trim() || null,
          });
          close();
          await onSaved();
        } catch (err) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Record Payment";
          errorSlot.textContent = err instanceof Error ? err.message : "Failed to record payment.";
          errorSlot.classList.remove("is-hidden");
        }
      });

      body.appendChild(form);
    },
  });
}

export function createPaymentsController({ onAuthExpired, onPaymentsChanged, onOpenInvoice }) {
  const viewState = {
    q: "",
    method: "all",
    page: 1,
    pageSize: 10,
    loading: false,
    error: null,
    data: null,
  };

  async function load(container) {
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      viewState.data = await fetchPayments({
        q: viewState.q,
        payment_method: viewState.method === "all" ? undefined : viewState.method,
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
      viewState.error = err instanceof Error ? err.message : "Failed to load payments.";
    }
    render(container);
  }

  function render(container) {
    container.replaceChildren();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Payments"));
    headingWrap.appendChild(
      createElement("p", "section-subtitle", "Record payments against issued invoices and track collections.")
    );
    const addBtn = createElement("button", "btn btn-primary", "+ Record Payment");
    addBtn.type = "button";
    addBtn.addEventListener("click", () => {
      void openRecordPaymentModal({
        onSaved: async () => {
          viewState.page = 1;
          await load(container);
          onPaymentsChanged();
        },
      }).catch((err) => {
        if (err?.status === 401) onAuthExpired();
      });
    });
    header.appendChild(headingWrap);
    header.appendChild(addBtn);
    container.appendChild(header);

    const card = createElement("section", "card");
    const toolbar = createElement("div", "toolbar");
    const filters = createElement("div", "toolbar-filters");

    const searchInput = createElement("input", "form-input toolbar-search");
    searchInput.type = "search";
    searchInput.placeholder = "Search invoice #, customer, reference...";
    searchInput.value = viewState.q;
    searchInput.setAttribute("aria-label", "Search payments");

    const methodSelect = createElement("select", "form-input toolbar-select");
    methodSelect.setAttribute("aria-label", "Filter by payment method");
    const allOpt = createElement("option", "", "All Methods");
    allOpt.value = "all";
    methodSelect.appendChild(allOpt);
    for (const [val, label] of PAYMENT_METHODS) {
      const opt = createElement("option", "", label);
      opt.value = val;
      if (viewState.method === val) opt.selected = true;
      methodSelect.appendChild(opt);
    }

    const searchBtn = createElement("button", "btn", "Search");
    searchBtn.type = "button";
    const applyFilter = () => {
      viewState.q = searchInput.value.trim();
      viewState.method = methodSelect.value;
      viewState.page = 1;
      void load(container);
    };
    searchBtn.addEventListener("click", applyFilter);
    methodSelect.addEventListener("change", applyFilter);
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        applyFilter();
      }
    });

    filters.appendChild(searchInput);
    filters.appendChild(methodSelect);
    filters.appendChild(searchBtn);
    toolbar.appendChild(filters);
    card.appendChild(toolbar);

    if (viewState.loading) {
      card.appendChild(createElement("p", "section-subtitle", "Loading payments..."));
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

    const items = viewState.data?.items || [];
    if (items.length === 0) {
      const empty = createElement("div", "empty-state");
      empty.appendChild(createElement("h3", "empty-state-title", "No payments recorded"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          viewState.q || viewState.method !== "all"
            ? "No payments match your search or method filter."
            : "Record payments against issued invoices to automatically update balances and invoice status."
        )
      );
      card.appendChild(empty);
      container.appendChild(card);
      return;
    }

    const scroll = createElement("div", "table-scroll");
    const table = createElement("table", "data-table");
    const thead = createElement("thead");
    const headRow = createElement("tr");
    for (const [label, cls] of [
      ["Date", ""],
      ["Invoice #", ""],
      ["Customer", ""],
      ["Method & Ref", ""],
      ["Amount", "cell-numeric"],
      ["", ""],
    ]) {
      headRow.appendChild(createElement("th", cls, label));
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = createElement("tbody");
    for (const pay of items) {
      const row = createElement("tr");
      row.appendChild(createElement("td", "", pay.payment_date));

      const invTd = createElement("td");
      const invBtn = createElement("button", "btn btn-sm", pay.invoice_number);
      invBtn.type = "button";
      invBtn.addEventListener("click", () => onOpenInvoice(pay.invoice_id));
      invTd.appendChild(invBtn);

      row.appendChild(invTd);
      row.appendChild(createElement("td", "", pay.customer_name));

      const methodTd = createElement("td");
      methodTd.appendChild(createElement("span", "cell-primary", formatMethodLabel(pay.payment_method)));
      if (pay.reference) {
        methodTd.appendChild(createElement("span", "cell-secondary", `Ref: ${pay.reference}`));
      }
      row.appendChild(methodTd);

      row.appendChild(
        createElement("td", "cell-numeric", formatCurrency(pay.amount, pay.currency_code))
      );

      const actionTd = createElement("td");
      const wrap = createElement("div", "table-actions");
      const delBtn = createElement("button", "btn btn-sm btn-danger-outline", "Reverse");
      delBtn.type = "button";
      delBtn.addEventListener("click", () => {
        openConfirmDialog({
          title: "Reverse Payment",
          message: `Reverse payment of ${formatCurrency(pay.amount, pay.currency_code)} on ${pay.invoice_number}?`,
          confirmLabel: "Reverse Payment",
          onConfirm: async () => {
            await deletePayment(pay.id);
            await load(container);
            onPaymentsChanged();
          },
        });
      });
      wrap.appendChild(delBtn);
      actionTd.appendChild(wrap);
      row.appendChild(actionTd);

      tbody.appendChild(row);
    }

    table.appendChild(tbody);
    scroll.appendChild(table);
    card.appendChild(scroll);

    card.appendChild(
      renderPaginationBar({
        page: viewState.data.page,
        totalPages: viewState.data.total_pages,
        total: viewState.data.total,
        onPageChange: (nextPage) => {
          viewState.page = nextPage;
          void load(container);
        },
      })
    );

    container.appendChild(card);
  }

  return {
    mount: (container) => load(container),
  };
}
