/**
 * Products / Services catalog management view with HSN code, pricing, and stock quantity.
 */

import {
  createProduct,
  deleteProduct,
  fetchProducts,
  updateProduct,
} from "/js/api.js";
import {
  createCheckboxField,
  createElement,
  createField,
  formatCurrency,
  renderPaginationBar,
} from "/js/dom.js";
import { openConfirmDialog, openModal } from "/js/modal.js";

function openProductModal({ product, currencyCode, onSaved }) {
  const isEdit = Boolean(product);
  openModal({
    title: isEdit ? `Edit Product #${product.id}` : "Add Product / Service",
    renderBody: (body, close) => {
      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");
      body.appendChild(errorSlot);

      const form = createElement("form", "form-stack");
      const grid = createElement("div", "form-grid");

      const fields = {
        name: createField({
          id: "prod-name",
          name: "name",
          label: "Product Name *",
          required: true,
          maxLength: 160,
          value: product?.name || "",
        }),
        sku: createField({
          id: "prod-sku",
          name: "sku",
          label: "SKU / Code",
          maxLength: 64,
          value: product?.sku || "",
        }),
        hsn_code: createField({
          id: "prod-hsn",
          name: "hsn_code",
          label: "HSN Code",
          maxLength: 16,
          placeholder: "e.g. 9983 or 847130",
          help: "Optional 4, 6, or 8 digit HSN/SAC code.",
          value: product?.hsn_code || "",
        }),
        unit: createField({
          id: "prod-unit",
          name: "unit",
          label: "Unit",
          maxLength: 32,
          placeholder: "hour, unit, pcs, month",
          value: product?.unit || "",
        }),
        purchase_price: createField({
          id: "prod-purchase-price",
          name: "purchase_price",
          label: `Purchase Price (${currencyCode})`,
          type: "number",
          min: 0,
          step: "0.01",
          value: product?.purchase_price ?? "",
        }),
        unit_price: createField({
          id: "prod-price",
          name: "unit_price",
          label: `Selling Price (${currencyCode}) *`,
          type: "number",
          required: true,
          min: 0,
          step: "0.01",
          value: product?.unit_price ?? "0.00",
        }),
        tax_rate: createField({
          id: "prod-tax-rate",
          name: "tax_rate",
          label: "GST Rate (%)",
          type: "number",
          required: true,
          min: 0,
          max: 100,
          step: "0.01",
          value: product?.tax_rate ?? "0.00",
        }),
        stock_quantity: createField({
          id: "prod-stock",
          name: "stock_quantity",
          label: "Stock Quantity",
          type: "number",
          required: true,
          min: 0,
          step: "0.01",
          value: product?.stock_quantity ?? "0.00",
        }),
        tax_label: createField({
          id: "prod-tax-label",
          name: "tax_label",
          label: "Tax Label",
          maxLength: 40,
          placeholder: "GST",
          value: product?.tax_label || "GST",
        }),
        description: createField({
          id: "prod-desc",
          name: "description",
          label: "Product Description",
          maxLength: 2000,
          fullWidth: true,
          value: product?.description || "",
        }),
        is_active: createCheckboxField({
          id: "prod-active",
          name: "is_active",
          label: "Active catalog item",
          checked: product ? product.is_active : true,
          fullWidth: true,
        }),
      };

      for (const field of Object.values(fields)) {
        grid.appendChild(field.wrapper);
      }
      form.appendChild(grid);

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Cancel");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);

      const submitBtn = createElement(
        "button",
        "btn btn-primary",
        isEdit ? "Save Changes" : "Create Item"
      );
      submitBtn.type = "submit";
      actions.appendChild(cancelBtn);
      actions.appendChild(submitBtn);
      form.appendChild(actions);

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        submitBtn.disabled = true;
        submitBtn.textContent = "Saving...";
        errorSlot.classList.add("is-hidden");

        const payload = {
          name: fields.name.input.value.trim(),
          sku: fields.sku.input.value.trim() || null,
          hsn_code: fields.hsn_code.input.value.trim() || null,
          description: fields.description.input.value.trim() || null,
          unit: fields.unit.input.value.trim() || null,
          purchase_price: fields.purchase_price.input.value.trim() || null,
          unit_price: fields.unit_price.input.value || "0.00",
          tax_rate: fields.tax_rate.input.value || "0.00",
          tax_label: fields.tax_label.input.value.trim() || null,
          stock_quantity: fields.stock_quantity.input.value || "0.00",
          is_active: fields.is_active.input.checked,
        };

        try {
          if (isEdit) {
            await updateProduct(product.id, payload);
          } else {
            await createProduct(payload);
          }
          close();
          await onSaved();
        } catch (err) {
          submitBtn.disabled = false;
          submitBtn.textContent = isEdit ? "Save Changes" : "Create Item";
          errorSlot.textContent = err instanceof Error ? err.message : "Failed to save item.";
          errorSlot.classList.remove("is-hidden");
        }
      });

      body.appendChild(form);
    },
  });
}

export function createProductsController({ getCurrencyCode, onAuthExpired, onCountsChanged }) {
  const viewState = {
    q: "",
    status: "all",
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
      const isActive =
        viewState.status === "active"
          ? true
          : viewState.status === "inactive"
          ? false
          : undefined;

      viewState.data = await fetchProducts({
        q: viewState.q,
        is_active: isActive,
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
      viewState.error = err instanceof Error ? err.message : "Failed to load catalog items.";
    }
    render(container);
  }

  function render(container) {
    const currencyCode = getCurrencyCode();
    container.replaceChildren();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Products / Services"));
    headingWrap.appendChild(
      createElement("p", "section-subtitle", "Manage catalog items, HSN codes, purchase/selling prices, GST rates, and stock.")
    );
    const addBtn = createElement("button", "btn btn-primary", "+ Add Item");
    addBtn.type = "button";
    addBtn.addEventListener("click", () => {
      openProductModal({
        product: null,
        currencyCode,
        onSaved: async () => {
          viewState.page = 1;
          await load(container);
          onCountsChanged();
        },
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
    searchInput.placeholder = "Search name, SKU, HSN code, description...";
    searchInput.value = viewState.q;
    searchInput.setAttribute("aria-label", "Search products and services");

    const statusSelect = createElement("select", "form-input toolbar-select");
    statusSelect.setAttribute("aria-label", "Filter items by status");
    for (const [val, label] of [
      ["all", "All Statuses"],
      ["active", "Active Only"],
      ["inactive", "Inactive Only"],
    ]) {
      const opt = createElement("option", "", label);
      opt.value = val;
      if (viewState.status === val) opt.selected = true;
      statusSelect.appendChild(opt);
    }

    const searchBtn = createElement("button", "btn", "Search");
    searchBtn.type = "button";
    const applySearch = () => {
      viewState.q = searchInput.value.trim();
      viewState.status = statusSelect.value;
      viewState.page = 1;
      void load(container);
    };
    searchBtn.addEventListener("click", applySearch);
    statusSelect.addEventListener("change", applySearch);
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        applySearch();
      }
    });

    filters.appendChild(searchInput);
    filters.appendChild(statusSelect);
    filters.appendChild(searchBtn);
    toolbar.appendChild(filters);
    card.appendChild(toolbar);

    if (viewState.loading) {
      card.appendChild(createElement("p", "section-subtitle", "Loading catalog items..."));
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
      empty.appendChild(createElement("h3", "empty-state-title", "No products or services found"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          viewState.q || viewState.status !== "all"
            ? "No catalog items match your current search or status filter."
            : "Add your first product or service to speed up invoice line-item entry."
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
      ["ID", ""],
      ["Product / SKU", ""],
      ["HSN Code", ""],
      ["Purchase", "cell-numeric"],
      ["Selling Price", "cell-numeric"],
      ["GST", "cell-numeric"],
      ["Stock", "cell-numeric"],
      ["Status", ""],
      ["", ""],
    ]) {
      headRow.appendChild(createElement("th", cls, label));
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = createElement("tbody");
    for (const product of items) {
      const row = createElement("tr");

      row.appendChild(createElement("td", "", `#${product.id}`));

      const nameCell = createElement("td");
      nameCell.appendChild(createElement("span", "cell-primary", product.name));
      const subParts = [product.sku ? `SKU: ${product.sku}` : null, product.description]
        .filter(Boolean)
        .join(" • ");
      if (subParts) {
        nameCell.appendChild(createElement("span", "cell-secondary", subParts));
      }

      const hsnCell = createElement("td", "", product.hsn_code || "—");

      const purchaseCell = createElement(
        "td",
        "cell-numeric",
        product.purchase_price !== null && product.purchase_price !== undefined
          ? formatCurrency(product.purchase_price, currencyCode)
          : "—"
      );

      const priceCell = createElement("td", "cell-numeric");
      const priceText = formatCurrency(product.unit_price, currencyCode);
      priceCell.textContent = product.unit ? `${priceText} / ${product.unit}` : priceText;

      const taxCell = createElement("td", "cell-numeric");
      const rateText = `${Number(product.tax_rate).toFixed(2)}%`;
      taxCell.textContent = product.tax_label ? `${product.tax_label} ${rateText}` : rateText;

      const stockCell = createElement(
        "td",
        "cell-numeric",
        Number(product.stock_quantity ?? 0).toFixed(2)
      );

      const statusCell = createElement("td");
      statusCell.appendChild(
        createElement(
          "span",
          product.is_active ? "badge badge-active" : "badge badge-inactive",
          product.is_active ? "Active" : "Inactive"
        )
      );

      const actionCell = createElement("td");
      const actionWrap = createElement("div", "table-actions");
      const editBtn = createElement("button", "btn btn-sm", "Edit");
      editBtn.type = "button";
      editBtn.addEventListener("click", () => {
        openProductModal({
          product,
          currencyCode,
          onSaved: async () => {
            await load(container);
            onCountsChanged();
          },
        });
      });

      const delBtn = createElement("button", "btn btn-sm btn-danger-outline", "Delete");
      delBtn.type = "button";
      delBtn.addEventListener("click", () => {
        openConfirmDialog({
          title: "Delete Item",
          message: `Delete "${product.name}"? This action cannot be undone.`,
          onConfirm: async () => {
            await deleteProduct(product.id);
            await load(container);
            onCountsChanged();
          },
        });
      });

      actionWrap.appendChild(editBtn);
      actionWrap.appendChild(delBtn);
      actionCell.appendChild(actionWrap);

      row.appendChild(nameCell);
      row.appendChild(hsnCell);
      row.appendChild(purchaseCell);
      row.appendChild(priceCell);
      row.appendChild(taxCell);
      row.appendChild(stockCell);
      row.appendChild(statusCell);
      row.appendChild(actionCell);
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
