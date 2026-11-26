/**
 * Reports & Audit Trail view: sales/GST summaries, HSN summary, CSV export, and audit events.
 */

import {
  fetchAuditEvents,
  fetchSalesSummary,
  getInvoicesCsvUrl,
} from "/js/api.js";
import {
  createElement,
  formatCurrency,
  renderPaginationBar,
} from "/js/dom.js";

export function createReportsController({ onAuthExpired }) {
  const viewState = {
    dateFrom: "",
    dateTo: "",
    auditAction: "",
    auditPage: 1,
    loading: false,
    error: null,
    summary: null,
    auditData: null,
  };

  async function load(container) {
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      const [summaryRes, auditRes] = await Promise.all([
        fetchSalesSummary({
          date_from: viewState.dateFrom || undefined,
          date_to: viewState.dateTo || undefined,
        }),
        fetchAuditEvents({
          action: viewState.auditAction || undefined,
          page: viewState.auditPage,
          page_size: 10,
        }),
      ]);
      viewState.summary = summaryRes;
      viewState.auditData = auditRes;
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load reports.";
    }
    render(container);
  }

  function render(container) {
    container.replaceChildren();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Reports & Audit Trail"));
    headingWrap.appendChild(
      createElement("p", "section-subtitle", "Review sales totals, GST/HSN breakdown, outstanding balances, and activity history.")
    );
    const csvLink = createElement("a", "btn btn-primary", "Export Invoices CSV");
    csvLink.href = getInvoicesCsvUrl({
      date_from: viewState.dateFrom || undefined,
      date_to: viewState.dateTo || undefined,
    });
    header.appendChild(headingWrap);
    header.appendChild(csvLink);
    container.appendChild(header);

    // Date filter toolbar card
    const filterCard = createElement("section", "card");
    const toolbar = createElement("div", "toolbar");
    const filters = createElement("div", "toolbar-filters");

    const fromInput = createElement("input", "form-input toolbar-select");
    fromInput.type = "date";
    fromInput.value = viewState.dateFrom;
    fromInput.setAttribute("aria-label", "Start date");

    const toInput = createElement("input", "form-input toolbar-select");
    toInput.type = "date";
    toInput.value = viewState.dateTo;
    toInput.setAttribute("aria-label", "End date");

    const applyBtn = createElement("button", "btn btn-primary", "Apply Dates");
    applyBtn.type = "button";
    applyBtn.addEventListener("click", () => {
      viewState.dateFrom = fromInput.value;
      viewState.dateTo = toInput.value;
      void load(container);
    });

    const clearBtn = createElement("button", "btn", "Clear");
    clearBtn.type = "button";
    clearBtn.addEventListener("click", () => {
      viewState.dateFrom = "";
      viewState.dateTo = "";
      void load(container);
    });

    filters.appendChild(createElement("span", "form-label", "From:"));
    filters.appendChild(fromInput);
    filters.appendChild(createElement("span", "form-label", "To:"));
    filters.appendChild(toInput);
    filters.appendChild(applyBtn);
    filters.appendChild(clearBtn);
    toolbar.appendChild(filters);
    filterCard.appendChild(toolbar);

    if (viewState.loading) {
      filterCard.appendChild(createElement("p", "section-subtitle", "Loading reports..."));
      container.appendChild(filterCard);
      return;
    }

    if (viewState.error) {
      const alert = createElement("div", "alert alert-error", viewState.error);
      alert.setAttribute("role", "alert");
      filterCard.appendChild(alert);
      container.appendChild(filterCard);
      return;
    }
    container.appendChild(filterCard);

    const s = viewState.summary;
    if (s) {
      const cur = s.currency_code || "USD";
      const metricsGrid = createElement("section", "metrics-grid");
      const cards = [
        {
          label: "Total Billed",
          value: formatCurrency(s.total_billed, cur),
          helper: `${s.total_invoices} total invoices (${s.draft_count} draft, ${s.void_count} cancelled)`,
        },
        {
          label: "Tax Billed",
          value: formatCurrency(s.total_tax, cur),
          helper: `CGST ${formatCurrency(s.total_cgst, cur)} • SGST ${formatCurrency(s.total_sgst, cur)} • IGST ${formatCurrency(s.total_igst, cur)}`,
        },
        {
          label: "Payments Collected",
          value: formatCurrency(s.total_collected_payments, cur),
          helper: "Recorded within selected dates",
        },
        {
          label: "Outstanding Balance",
          value: formatCurrency(s.total_outstanding, cur),
          helper: `${s.overdue_count} overdue invoice(s)`,
        },
      ];
      for (const item of cards) {
        const c = createElement("article", "card");
        c.appendChild(createElement("p", "metric-label", item.label));
        c.appendChild(createElement("p", "metric-value", item.value));
        c.appendChild(createElement("p", "metric-helper", item.helper));
        metricsGrid.appendChild(c);
      }
      container.appendChild(metricsGrid);

      // Breakdown & Top Customers grid
      const tablesGrid = createElement("div", "content-grid");

      const topCustCard = createElement("section", "card");
      const topHeader = createElement("div", "card-header");
      topHeader.appendChild(createElement("h3", "card-title", "Top Customers by Billed Amount"));
      topCustCard.appendChild(topHeader);

      if (!s.top_customers || s.top_customers.length === 0) {
        topCustCard.appendChild(createElement("p", "section-subtitle", "No billed customer invoices in this range."));
      } else {
        const scroll = createElement("div", "table-scroll");
        const tbl = createElement("table", "data-table");
        const thead = createElement("thead");
        const hrow = createElement("tr");
        for (const [lbl, cls] of [
          ["Customer", ""],
          ["Invoices", "cell-numeric"],
          ["Billed", "cell-numeric"],
          ["Balance", "cell-numeric"],
        ]) {
          hrow.appendChild(createElement("th", cls, lbl));
        }
        thead.appendChild(hrow);
        tbl.appendChild(thead);

        const tbody = createElement("tbody");
        for (const cust of s.top_customers) {
          const r = createElement("tr");
          r.appendChild(createElement("td", "cell-primary", cust.customer_name));
          r.appendChild(createElement("td", "cell-numeric", String(cust.invoice_count)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(cust.total_billed, cur)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(cust.balance_due, cur)));
          tbody.appendChild(r);
        }
        tbl.appendChild(tbody);
        scroll.appendChild(tbl);
        topCustCard.appendChild(scroll);
      }

      const statusCard = createElement("section", "card");
      const statusHeader = createElement("div", "card-header");
      statusHeader.appendChild(createElement("h3", "card-title", "Invoice Status Breakdown"));
      statusCard.appendChild(statusHeader);

      const stScroll = createElement("div", "table-scroll");
      const stTable = createElement("table", "data-table");
      const stHead = createElement("thead");
      const stHeadRow = createElement("tr");
      for (const [lbl, cls] of [
        ["Status", ""],
        ["Count", "cell-numeric"],
        ["Amount", "cell-numeric"],
      ]) {
        stHeadRow.appendChild(createElement("th", cls, lbl));
      }
      stHead.appendChild(stHeadRow);
      stTable.appendChild(stHead);

      const stBody = createElement("tbody");
      for (const rowItem of s.status_breakdown || []) {
        const r = createElement("tr");
        const stTd = createElement("td");
        stTd.appendChild(
          createElement(
            "span",
            `badge badge-${rowItem.status}`,
            rowItem.status.replace("_", " ")
          )
        );
        r.appendChild(stTd);
        r.appendChild(createElement("td", "cell-numeric", String(rowItem.count)));
        r.appendChild(createElement("td", "cell-numeric", formatCurrency(rowItem.total_amount, cur)));
        stBody.appendChild(r);
      }
      stTable.appendChild(stBody);
      stScroll.appendChild(stTable);
      statusCard.appendChild(stScroll);

      tablesGrid.appendChild(topCustCard);
      tablesGrid.appendChild(statusCard);
      container.appendChild(tablesGrid);

      // HSN Summary Table
      const hsnCard = createElement("section", "card");
      const hsnHeader = createElement("div", "card-header");
      hsnHeader.appendChild(createElement("h3", "card-title", "HSN Summary"));
      hsnCard.appendChild(hsnHeader);

      const hsnRows = s.hsn_summary || [];
      if (hsnRows.length === 0) {
        hsnCard.appendChild(
          createElement("p", "section-subtitle", "No billed invoice items in the selected date range.")
        );
      } else {
        const hScroll = createElement("div", "table-scroll");
        const hTable = createElement("table", "data-table");
        const hHead = createElement("thead");
        const hHeadRow = createElement("tr");
        for (const [lbl, cls] of [
          ["HSN Code", ""],
          ["Qty", "cell-numeric"],
          ["Taxable Value", "cell-numeric"],
          ["CGST", "cell-numeric"],
          ["SGST", "cell-numeric"],
          ["IGST", "cell-numeric"],
          ["Total Tax", "cell-numeric"],
          ["Total Value", "cell-numeric"],
        ]) {
          hHeadRow.appendChild(createElement("th", cls, lbl));
        }
        hHead.appendChild(hHeadRow);
        hTable.appendChild(hHead);

        const hBody = createElement("tbody");
        for (const h of hsnRows) {
          const r = createElement("tr");
          r.appendChild(createElement("td", "cell-primary", h.hsn_code));
          r.appendChild(createElement("td", "cell-numeric", Number(h.total_quantity).toFixed(2)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(h.taxable_value, cur)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(h.cgst_amount, cur)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(h.sgst_amount, cur)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(h.igst_amount, cur)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(h.total_tax, cur)));
          r.appendChild(createElement("td", "cell-numeric", formatCurrency(h.total_value, cur)));
          hBody.appendChild(r);
        }
        hTable.appendChild(hBody);
        hScroll.appendChild(hTable);
        hsnCard.appendChild(hScroll);
      }
      container.appendChild(hsnCard);
    }

    // Audit Events Table
    const auditCard = createElement("section", "card");
    const auditHeader = createElement("div", "card-header");
    auditHeader.appendChild(createElement("h3", "card-title", "Recent Audit Events"));
    auditCard.appendChild(auditHeader);

    const auditItems = viewState.auditData?.items || [];
    if (auditItems.length === 0) {
      auditCard.appendChild(createElement("p", "section-subtitle", "No audit events recorded."));
    } else {
      const aScroll = createElement("div", "table-scroll");
      const aTable = createElement("table", "data-table");
      const aHead = createElement("thead");
      const aHeadRow = createElement("tr");
      for (const lbl of ["Timestamp", "Action", "Entity", "Details"]) {
        aHeadRow.appendChild(createElement("th", "", lbl));
      }
      aHead.appendChild(aHeadRow);
      aTable.appendChild(aHead);

      const aBody = createElement("tbody");
      for (const ev of auditItems) {
        const r = createElement("tr");
        const ts = new Date(ev.created_at).toLocaleString();
        r.appendChild(createElement("td", "", ts));
        r.appendChild(createElement("td", "cell-primary", ev.action));
        r.appendChild(
          createElement(
            "td",
            "",
            ev.entity_id ? `${ev.entity_type} #${ev.entity_id}` : ev.entity_type
          )
        );
        const detailsText = ev.details_json ? JSON.stringify(ev.details_json) : "—";
        r.appendChild(createElement("td", "cell-secondary", detailsText));
        aBody.appendChild(r);
      }
      aTable.appendChild(aBody);
      aScroll.appendChild(aTable);
      auditCard.appendChild(aScroll);

      auditCard.appendChild(
        renderPaginationBar({
          page: viewState.auditData.page,
          totalPages: viewState.auditData.total_pages,
          total: viewState.auditData.total,
          onPageChange: (nextPage) => {
            viewState.auditPage = nextPage;
            void load(container);
          },
        })
      );
    }
    container.appendChild(auditCard);
  }

  return {
    mount: (container) => load(container),
  };
}
