/**
 * Notifications & Operational Alerts view backed by overdue invoices, stock levels, and audit history.
 */

import {
  fetchAuditEvents,
  fetchBusinessNotifications,
  fetchInvoices,
  fetchProducts,
  markAllBusinessNotificationsRead,
  markBusinessNotificationRead,
} from "/js/api.js";
import { createElement, formatCurrency } from "/js/dom.js";

export function createNotificationsController({ onAuthExpired, onNavigate }) {
  const viewState = {
    loading: false,
    error: null,
    overdueInvoices: [],
    lowStockItems: [],
    recentAudit: [],
    saasAlerts: [],
  };

  async function load(container) {
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      const [overdueRes, productsRes, auditRes, saasRes] = await Promise.all([
        fetchInvoices({ status: "overdue", page: 1, page_size: 20 }),
        fetchProducts({ is_active: true, page: 1, page_size: 100 }),
        fetchAuditEvents({ page: 1, page_size: 15 }),
        fetchBusinessNotifications({ limit: 30 }).catch(() => ({ items: [] })),
      ]);

      viewState.overdueInvoices = overdueRes.items || [];
      viewState.lowStockItems = (productsRes.items || []).filter(
        (p) => Number(p.stock_quantity ?? 0) <= 5
      );
      viewState.recentAudit = auditRes.items || [];
      viewState.saasAlerts = saasRes?.items || [];
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load notifications.";
    }
    render(container);
  }

  function render(container) {
    container.replaceChildren();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Notifications & Alerts"));
    headingWrap.appendChild(
      createElement(
        "p",
        "section-subtitle",
        "Live billing alerts for overdue invoices, low inventory stock, and recent account activity."
      )
    );
    const refreshBtn = createElement("button", "btn", "Refresh");
    refreshBtn.type = "button";
    refreshBtn.addEventListener("click", () => void load(container));
    header.appendChild(headingWrap);
    header.appendChild(refreshBtn);
    container.appendChild(header);

    if (viewState.loading) {
      const card = createElement("section", "card");
      card.appendChild(createElement("p", "section-subtitle", "Checking alerts and recent events..."));
      container.appendChild(card);
      return;
    }

    if (viewState.error) {
      const alert = createElement("div", "alert alert-error", viewState.error);
      alert.setAttribute("role", "alert");
      container.appendChild(alert);
      return;
    }

    const grid = createElement("div", "content-grid");

    // Left: Actionable billing & stock alerts
    const alertsCard = createElement("section", "card");
    const alertsHeader = createElement("div", "card-header");
    alertsHeader.appendChild(createElement("h3", "card-title", "Action Needed"));
    alertsCard.appendChild(alertsHeader);

    if (viewState.overdueInvoices.length === 0 && viewState.lowStockItems.length === 0) {
      const empty = createElement("div", "empty-state");
      empty.appendChild(createElement("h4", "empty-state-title", "All caught up"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          "No overdue invoices or low-stock warnings at the moment."
        )
      );
      alertsCard.appendChild(empty);
    } else {
      const list = createElement("div", "history-list");

      for (const inv of viewState.overdueInvoices) {
        const item = createElement("div", "history-item");
        const head = createElement("div", "history-item-head");
        head.appendChild(
          createElement(
            "strong",
            "",
            `Overdue Invoice: ${inv.invoice_number} (${inv.customer?.name || "Customer"})`
          )
        );
        head.appendChild(createElement("span", "badge badge-overdue", "Overdue"));
        item.appendChild(head);
        item.appendChild(
          createElement(
            "p",
            "history-item-meta",
            `Balance Due: ${formatCurrency(inv.balance_due, inv.currency_code)} • Due ${inv.due_date}`
          )
        );
        const openBtn = createElement("button", "btn btn-sm", "Open Invoice");
        openBtn.type = "button";
        openBtn.addEventListener("click", () => onNavigate(`invoice:${inv.id}`));
        item.appendChild(openBtn);
        list.appendChild(item);
      }

      for (const prod of viewState.lowStockItems) {
        const qty = Number(prod.stock_quantity ?? 0);
        const item = createElement("div", "history-item");
        const head = createElement("div", "history-item-head");
        head.appendChild(createElement("strong", "", `Stock Alert: ${prod.name}`));
        head.appendChild(
          createElement(
            "span",
            `badge ${qty <= 0 ? "badge-overdue" : "badge-partially_paid"}`,
            qty <= 0 ? "Out of Stock" : `Low Stock (${qty.toFixed(0)})`
          )
        );
        item.appendChild(head);
        const invBtn = createElement("button", "btn btn-sm", "Review in Inventory");
        invBtn.type = "button";
        invBtn.addEventListener("click", () => onNavigate("inventory"));
        item.appendChild(invBtn);
        list.appendChild(item);
      }

      alertsCard.appendChild(list);
    }

    // Right: Recent account audit log
    const activityCard = createElement("section", "card");
    const actHeader = createElement("div", "card-header");
    actHeader.appendChild(createElement("h3", "card-title", "Recent Activity"));
    const reportsBtn = createElement("button", "btn btn-sm", "Full Reports");
    reportsBtn.type = "button";
    reportsBtn.addEventListener("click", () => onNavigate("reports"));
    actHeader.appendChild(reportsBtn);
    activityCard.appendChild(actHeader);

    if (viewState.recentAudit.length === 0) {
      activityCard.appendChild(createElement("p", "section-subtitle", "No recent audit events yet."));
    } else {
      const actList = createElement("div", "history-list");
      for (const ev of viewState.recentAudit) {
        const entry = createElement("div", "history-item");
        const head = createElement("div", "history-item-head");
        head.appendChild(createElement("strong", "", ev.action));
        head.appendChild(
          createElement("span", "cell-secondary", new Date(ev.created_at).toLocaleString())
        );
        entry.appendChild(head);
        entry.appendChild(
          createElement(
            "p",
            "history-item-meta",
            `${ev.entity_type}${ev.entity_id ? ` #${ev.entity_id}` : ""}`
          )
        );
        actList.appendChild(entry);
      }
      activityCard.appendChild(actList);
    }

    grid.appendChild(alertsCard);
    grid.appendChild(activityCard);
    container.appendChild(grid);

    // SaaS & Subscription Notices section
    const saasCard = createElement("section", "card");
    const saasHeader = createElement("div", "card-header");
    saasHeader.appendChild(createElement("h3", "card-title", "Subscription & Account Notices"));
    const markAllBtn = createElement("button", "btn btn-sm", "Mark All Read");
    markAllBtn.type = "button";
    markAllBtn.disabled = viewState.saasAlerts.every((n) => n.is_read);
    markAllBtn.addEventListener("click", async () => {
      await markAllBusinessNotificationsRead();
      await load(container);
    });
    saasHeader.appendChild(markAllBtn);
    saasCard.appendChild(saasHeader);

    if (viewState.saasAlerts.length === 0) {
      saasCard.appendChild(
        createElement("p", "section-subtitle", "No subscription or system notices yet.")
      );
    } else {
      const noticeList = createElement("div", "history-list");
      for (const note of viewState.saasAlerts) {
        const item = createElement("div", "history-item");
        const head = createElement("div", "history-item-head");
        head.appendChild(createElement("strong", "", note.title));
        head.appendChild(
          createElement(
            "span",
            `badge ${note.is_read ? "badge-draft" : "badge-partially_paid"}`,
            note.is_read ? "Read" : note.severity?.toUpperCase() || "NEW"
          )
        );
        item.appendChild(head);
        item.appendChild(createElement("p", "history-item-meta", note.message));
        const metaRow = createElement("div", "topbar-actions");
        metaRow.appendChild(
          createElement("span", "cell-secondary", new Date(note.created_at).toLocaleString())
        );
        if (!note.is_read) {
          const readBtn = createElement("button", "btn btn-sm", "Mark Read");
          readBtn.type = "button";
          readBtn.addEventListener("click", async () => {
            await markBusinessNotificationRead(note.id);
            await load(container);
          });
          metaRow.appendChild(readBtn);
        }
        item.appendChild(metaRow);
        noticeList.appendChild(item);
      }
      saasCard.appendChild(noticeList);
    }
    container.appendChild(saasCard);
  }

  return {
    mount(container) {
      return load(container);
    },
  };
}
