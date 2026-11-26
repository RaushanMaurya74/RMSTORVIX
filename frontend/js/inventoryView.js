/**
 * Inventory & Stock management view backed by live catalog products (/api/v1/products).
 */

import { adjustProductStock, fetchAuditEvents, fetchProducts, updateProduct } from "/js/api.js";
import {
  createElement,
  createField,
  formatCurrency,
  renderPaginationBar,
  showToast,
} from "/js/dom.js";
import { openModal } from "/js/modal.js";

const LOW_STOCK_THRESHOLD = 5;

function getStockStatus(qty) {
  const numeric = Number(qty ?? 0);
  if (numeric <= 0) {
    return { key: "out", label: "Out of Stock", badgeClass: "badge-overdue" };
  }
  if (numeric <= LOW_STOCK_THRESHOLD) {
    return { key: "low", label: "Low Stock", badgeClass: "badge-partially_paid" };
  }
  return { key: "ok", label: "In Stock", badgeClass: "badge-paid" };
}

function openStockPurchaseAdjustModal({ product, onSaved }) {
  openModal({
    title: `Stock Purchase / Adjust — ${product.name}`,
    small: true,
    renderBody: (body, close) => {
      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");
      body.appendChild(errorSlot);

      const form = createElement("form", "form-stack");
      const deltaField = createField({
        id: "inv-delta-qty",
        name: "delta_quantity",
        label: "Adjustment Delta (+/-) *",
        type: "number",
        required: true,
        step: "0.01",
        placeholder: "e.g. 25 to add stock, -5 to write off",
        help: `Current stock: ${Number(product.stock_quantity ?? 0).toFixed(2)} ${product.unit || "units"}.`,
      });
      const reasonField = createField({
        id: "inv-delta-reason",
        name: "reason",
        label: "Movement Reason",
        maxLength: 250,
        placeholder: "e.g. Supplier purchase PO-2026-11 / Damaged stock",
      });

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Cancel");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);
      const saveBtn = createElement("button", "btn btn-primary", "Apply Adjustment");
      saveBtn.type = "submit";
      actions.append(cancelBtn, saveBtn);
      form.append(deltaField.wrapper, reasonField.wrapper, actions);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        saveBtn.disabled = true;
        errorSlot.classList.add("is-hidden");
        try {
          await adjustProductStock(product.id, {
            delta_quantity: deltaField.input.value.trim(),
            reason: reasonField.input.value.trim() || null,
          });
          showToast(`Stock movement recorded for "${product.name}".`, "success");
          close();
          await onSaved();
        } catch (err) {
          saveBtn.disabled = false;
          errorSlot.textContent = err instanceof Error ? err.message : "Adjustment failed.";
          errorSlot.classList.remove("is-hidden");
        }
      });
      body.appendChild(form);
    },
  });
}

function openStockAdjustModal({ product, onSaved }) {
  openModal({
    title: `Update Stock — ${product.name}`,
    small: true,
    renderBody: (body, close) => {
      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");
      body.appendChild(errorSlot);

      const form = createElement("form", "form-stack");
      const qtyField = createField({
        id: "inv-stock-qty",
        name: "stock_quantity",
        label: "Current Stock Quantity *",
        type: "number",
        required: true,
        min: 0,
        step: "0.01",
        value: product.stock_quantity ?? "0.00",
        help: product.unit ? `Measured in ${product.unit}` : "Available inventory units.",
      });
      form.appendChild(qtyField.wrapper);

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Cancel");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);

      const saveBtn = createElement("button", "btn btn-primary", "Update Stock");
      saveBtn.type = "submit";
      actions.appendChild(cancelBtn);
      actions.appendChild(saveBtn);
      form.appendChild(actions);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        saveBtn.disabled = true;
        saveBtn.textContent = "Saving...";
        errorSlot.classList.add("is-hidden");

        try {
          await updateProduct(product.id, {
            name: product.name,
            sku: product.sku,
            hsn_code: product.hsn_code,
            description: product.description,
            unit: product.unit,
            purchase_price: product.purchase_price,
            unit_price: product.unit_price,
            tax_rate: product.tax_rate,
            tax_label: product.tax_label,
            stock_quantity: qtyField.input.value.trim() || "0.00",
            is_active: product.is_active,
          });
          showToast(`Updated stock for "${product.name}".`, "success");
          close();
          await onSaved();
        } catch (err) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Update Stock";
          errorSlot.textContent = err instanceof Error ? err.message : "Failed to update stock.";
          errorSlot.classList.remove("is-hidden");
        }
      });

      body.appendChild(form);
    },
  });
}

export function createInventoryController({ getCurrencyCode, onAuthExpired, onInventoryChanged }) {
  const viewState = {
    q: "",
    stockFilter: "all", // all | low | out | ok
    page: 1,
    pageSize: 10,
    loading: false,
    error: null,
    items: [],
    movements: [],
  };

  async function load(container) {
    viewState.loading = true;
    viewState.error = null;
    render(container);

    try {
      const [res, auditRes] = await Promise.all([
        fetchProducts({
          q: viewState.q || undefined,
          page: 1,
          page_size: 100,
        }),
        fetchAuditEvents({ page: 1, page_size: 40 }).catch(() => ({ items: [] })),
      ]);
      viewState.items = res.items || [];
      viewState.movements = (auditRes?.items || []).filter((ev) =>
        String(ev.action || "").startsWith("stock.") || ev.action === "product.created"
      );
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load inventory.";
    }
    render(container);
  }

  function render(container) {
    const currencyCode = getCurrencyCode() || "USD";
    container.replaceChildren();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Inventory / Stock"));
    headingWrap.appendChild(
      createElement(
        "p",
        "section-subtitle",
        "Monitor product stock levels, identify low or depleted items, and update available quantities."
      )
    );
    header.appendChild(headingWrap);
    container.appendChild(header);

    const allItems = viewState.items;
    const outCount = allItems.filter((p) => Number(p.stock_quantity ?? 0) <= 0).length;
    const lowCount = allItems.filter((p) => {
      const q = Number(p.stock_quantity ?? 0);
      return q > 0 && q <= LOW_STOCK_THRESHOLD;
    }).length;
    const healthyCount = allItems.filter((p) => Number(p.stock_quantity ?? 0) > LOW_STOCK_THRESHOLD).length;
    const totalValuation = allItems.reduce((sum, p) => {
      const q = Number(p.stock_quantity ?? 0);
      const unitCost = Number(p.purchase_price ?? p.unit_price ?? 0);
      return sum + q * unitCost;
    }, 0);

    const metrics = createElement("section", "metrics-grid");
    for (const [label, value, helper] of [
      ["Tracked SKUs", String(allItems.length), "Catalog products & services"],
      ["In Stock", String(healthyCount), `Above ${LOW_STOCK_THRESHOLD} units`],
      ["Low / Out of Stock", `${lowCount} / ${outCount}`, "Restock attention needed"],
      ["Est. Stock Value", formatCurrency(totalValuation, currencyCode), "Based on purchase/unit price"],
    ]) {
      const mCard = createElement("article", "card");
      mCard.appendChild(createElement("p", "metric-label", label));
      mCard.appendChild(createElement("p", "metric-value", value));
      mCard.appendChild(createElement("p", "metric-helper", helper));
      metrics.appendChild(mCard);
    }
    container.appendChild(metrics);

    const card = createElement("section", "card");
    const toolbar = createElement("div", "toolbar");
    const filters = createElement("div", "toolbar-filters");

    const searchInput = createElement("input", "form-input toolbar-search");
    searchInput.type = "search";
    searchInput.placeholder = "Search SKU, HSN, or item name...";
    searchInput.value = viewState.q;
    searchInput.setAttribute("aria-label", "Search inventory");

    const stockSelect = createElement("select", "form-input toolbar-select");
    stockSelect.setAttribute("aria-label", "Filter by stock level");
    for (const [val, label] of [
      ["all", "All Stock Levels"],
      ["low", `Low Stock (<= ${LOW_STOCK_THRESHOLD})`],
      ["out", "Out of Stock (0)"],
      ["ok", "Healthy Stock"],
    ]) {
      const opt = createElement("option", "", label);
      opt.value = val;
      if (viewState.stockFilter === val) opt.selected = true;
      stockSelect.appendChild(opt);
    }

    const searchBtn = createElement("button", "btn", "Search");
    searchBtn.type = "button";
    searchBtn.addEventListener("click", () => {
      viewState.q = searchInput.value.trim();
      viewState.stockFilter = stockSelect.value;
      viewState.page = 1;
      void load(container);
    });
    stockSelect.addEventListener("change", () => {
      viewState.stockFilter = stockSelect.value;
      viewState.page = 1;
      render(container);
    });
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        searchBtn.click();
      }
    });

    filters.appendChild(searchInput);
    filters.appendChild(stockSelect);
    filters.appendChild(searchBtn);
    toolbar.appendChild(filters);
    card.appendChild(toolbar);

    if (viewState.loading) {
      card.appendChild(createElement("p", "section-subtitle", "Loading inventory levels..."));
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

    const filtered = allItems.filter((item) => {
      if (viewState.stockFilter === "all") return true;
      return getStockStatus(item.stock_quantity).key === viewState.stockFilter;
    });

    const total = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / viewState.pageSize));
    if (viewState.page > totalPages) viewState.page = totalPages;
    const startIdx = (viewState.page - 1) * viewState.pageSize;
    const pageItems = filtered.slice(startIdx, startIdx + viewState.pageSize);

    if (pageItems.length === 0) {
      const empty = createElement("div", "empty-state");
      empty.appendChild(createElement("h3", "empty-state-title", "No inventory items match"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          "Add products in Products / Services or adjust your search and stock filter."
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
      ["Item", ""],
      ["SKU", ""],
      ["HSN", ""],
      ["Selling Price", "cell-numeric"],
      ["Stock Qty", "cell-numeric"],
      ["Level", ""],
      ["", ""],
    ]) {
      headRow.appendChild(createElement("th", cls, label));
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = createElement("tbody");
    for (const item of pageItems) {
      const row = createElement("tr");
      const nameCell = createElement("td");
      nameCell.appendChild(createElement("span", "cell-primary", item.name));
      if (item.unit) {
        nameCell.appendChild(createElement("span", "cell-secondary", `Unit: ${item.unit}`));
      }

      const status = getStockStatus(item.stock_quantity);
      const levelCell = createElement("td");
      levelCell.appendChild(createElement("span", `badge ${status.badgeClass}`, status.label));

      const actionCell = createElement("td");
      const actionsWrap = createElement("div", "table-actions");
      const moveBtn = createElement("button", "btn btn-sm btn-primary", "+/- Move");
      moveBtn.type = "button";
      moveBtn.addEventListener("click", () => {
        openStockPurchaseAdjustModal({
          product: item,
          onSaved: async () => {
            onInventoryChanged?.();
            await load(container);
          },
        });
      });
      const adjustBtn = createElement("button", "btn btn-sm", "Set Qty");
      adjustBtn.type = "button";
      adjustBtn.addEventListener("click", () => {
        openStockAdjustModal({
          product: item,
          onSaved: async () => {
            onInventoryChanged?.();
            await load(container);
          },
        });
      });
      actionsWrap.append(moveBtn, adjustBtn);
      actionCell.appendChild(actionsWrap);

      row.appendChild(nameCell);
      row.appendChild(createElement("td", "", item.sku || "—"));
      row.appendChild(createElement("td", "", item.hsn_code || "—"));
      row.appendChild(
        createElement("td", "cell-numeric", formatCurrency(item.unit_price, currencyCode))
      );
      row.appendChild(
        createElement("td", "cell-numeric", Number(item.stock_quantity ?? 0).toFixed(2))
      );
      row.appendChild(levelCell);
      row.appendChild(actionCell);
      tbody.appendChild(row);
    }

    table.appendChild(tbody);
    scroll.appendChild(table);
    card.appendChild(scroll);

    card.appendChild(
      renderPaginationBar({
        page: viewState.page,
        totalPages,
        total,
        onPageChange: (nextPage) => {
          viewState.page = nextPage;
          render(container);
        },
      })
    );

    container.appendChild(card);

    const moveCard = createElement("section", "card");
    moveCard.appendChild(createElement("h3", "card-title", "Recent Stock Movements"));
    if (viewState.movements.length === 0) {
      moveCard.appendChild(createElement("p", "section-subtitle", "No stock adjustments or invoice deductions recorded yet."));
    } else {
      const mList = createElement("div", "history-list");
      for (const mv of viewState.movements.slice(0, 10)) {
        const entry = createElement("div", "history-item");
        const head = createElement("div", "history-item-head");
        head.appendChild(createElement("strong", "", mv.action));
        head.appendChild(createElement("span", "cell-secondary", new Date(mv.created_at).toLocaleString()));
        entry.appendChild(head);
        entry.appendChild(
          createElement(
            "p",
            "history-item-meta",
            mv.details_json ? JSON.stringify(mv.details_json) : `${mv.entity_type} #${mv.entity_id || ""}`
          )
        );
        mList.appendChild(entry);
      }
      moveCard.appendChild(mList);
    }
    container.appendChild(moveCard);
  }

  return {
    mount(container) {
      return load(container);
    },
  };
}
