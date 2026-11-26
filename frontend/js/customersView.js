/**
 * Customers management view: search, filter, pagination, GSTIN verification, and modal CRUD.
 */

import {
  createCustomer,
  deleteCustomer,
  fetchCustomers,
  updateCustomer,
  verifyCustomerGstin,
} from "/js/api.js";
import {
  createCheckboxField,
  createElement,
  createField,
  renderPaginationBar,
} from "/js/dom.js";
import { openConfirmDialog, openModal } from "/js/modal.js";

function openCustomerModal({ customer, onSaved }) {
  const isEdit = Boolean(customer);
  openModal({
    title: isEdit ? "Edit Customer" : "Add Customer",
    renderBody: (body, close) => {
      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");
      body.appendChild(errorSlot);

      const gstinNotice = createElement("div", "alert is-hidden");
      gstinNotice.setAttribute("role", "status");
      body.appendChild(gstinNotice);

      let isGstinVerified = Boolean(customer?.gstin_verified);

      const form = createElement("form", "form-stack");
      const grid = createElement("div", "form-grid");

      const fields = {
        name: createField({
          id: "cust-name",
          name: "name",
          label: "Customer Name *",
          required: true,
          maxLength: 160,
          value: customer?.name || "",
        }),
        company_name: createField({
          id: "cust-company",
          name: "company_name",
          label: "Company Name",
          maxLength: 180,
          value: customer?.company_name || "",
        }),
        email: createField({
          id: "cust-email",
          name: "email",
          label: "Email",
          type: "email",
          maxLength: 254,
          value: customer?.email || "",
        }),
        phone: createField({
          id: "cust-phone",
          name: "phone",
          label: "Phone",
          maxLength: 40,
          value: customer?.phone || "",
        }),
      };

      // Custom GSTIN / Tax ID field with Verify GSTIN button
      const taxWrap = createElement("div", "form-field form-field-full");
      const taxLabel = createElement("label", "form-label", "GSTIN / Tax ID");
      taxLabel.setAttribute("for", "cust-tax-id");
      const taxRow = createElement("div", "input-with-action");
      const taxInput = createElement("input", "form-input");
      taxInput.id = "cust-tax-id";
      taxInput.name = "tax_id";
      taxInput.maxLength = 64;
      taxInput.placeholder = "15-character GSTIN (e.g. 27AAACP1234A1Z5)";
      taxInput.value = customer?.tax_id || "";

      const verifyBtn = createElement("button", "btn", "Verify GSTIN");
      verifyBtn.type = "button";
      taxRow.appendChild(taxInput);
      taxRow.appendChild(verifyBtn);
      taxWrap.appendChild(taxLabel);
      taxWrap.appendChild(taxRow);
      taxWrap.appendChild(
        createElement(
          "span",
          "form-help",
          "Verifies 15-char GSTIN checksum, extracts state/country, and auto-fills registered details when external lookup is configured."
        )
      );

      const addrFields = {
        address_line1: createField({
          id: "cust-addr1",
          name: "address_line1",
          label: "Address Line 1",
          maxLength: 200,
          fullWidth: true,
          value: customer?.address_line1 || "",
        }),
        address_line2: createField({
          id: "cust-addr2",
          name: "address_line2",
          label: "Address Line 2",
          maxLength: 200,
          fullWidth: true,
          value: customer?.address_line2 || "",
        }),
        city: createField({
          id: "cust-city",
          name: "city",
          label: "City",
          maxLength: 100,
          value: customer?.city || "",
        }),
        state: createField({
          id: "cust-state",
          name: "state",
          label: "State / Province",
          maxLength: 100,
          value: customer?.state || "",
        }),
        postal_code: createField({
          id: "cust-postal",
          name: "postal_code",
          label: "Postal Code",
          maxLength: 30,
          value: customer?.postal_code || "",
        }),
        country: createField({
          id: "cust-country",
          name: "country",
          label: "Country",
          maxLength: 100,
          value: customer?.country || "",
        }),
        notes: createField({
          id: "cust-notes",
          name: "notes",
          label: "Notes",
          maxLength: 2000,
          fullWidth: true,
          value: customer?.notes || "",
        }),
        is_active: createCheckboxField({
          id: "cust-active",
          name: "is_active",
          label: "Active customer",
          checked: customer ? customer.is_active : true,
          fullWidth: true,
        }),
      };

      for (const field of Object.values(fields)) {
        grid.appendChild(field.wrapper);
      }
      grid.appendChild(taxWrap);
      for (const field of Object.values(addrFields)) {
        grid.appendChild(field.wrapper);
      }
      form.appendChild(grid);

      taxInput.addEventListener("input", () => {
        isGstinVerified = false;
        gstinNotice.classList.add("is-hidden");
      });

      verifyBtn.addEventListener("click", async () => {
        const raw = taxInput.value.trim().toUpperCase();
        if (!raw) {
          gstinNotice.className = "alert alert-error";
          gstinNotice.textContent = "Enter a 15-character GSTIN first.";
          return;
        }
        verifyBtn.disabled = true;
        verifyBtn.textContent = "Verifying...";
        gstinNotice.classList.add("is-hidden");

        try {
          const result = await verifyCustomerGstin(raw);
          taxInput.value = result.gstin;
          if (result.valid) {
            isGstinVerified = true;
            const metaParts = [result.message];
            if (result.legal_name) metaParts.push(`Legal: ${result.legal_name}`);
            if (result.trade_name) metaParts.push(`Trade: ${result.trade_name}`);
            if (result.gstin_status) metaParts.push(`Status: ${result.gstin_status}`);
            if (result.state_code && result.state) {
              metaParts.push(`State: ${result.state} (${result.state_code})`);
            }
            gstinNotice.className = "alert alert-success";
            gstinNotice.textContent = metaParts.join(" • ");

            const resolvedCompany = result.trade_name || result.legal_name || result.company_name;
            if (resolvedCompany) {
              fields.company_name.input.value = resolvedCompany;
              if (!fields.name.input.value.trim()) {
                fields.name.input.value = result.legal_name || resolvedCompany;
              }
            }
            if (result.address_line1) addrFields.address_line1.input.value = result.address_line1;
            if (result.address_line2) addrFields.address_line2.input.value = result.address_line2;
            if (result.city) addrFields.city.input.value = result.city;
            if (result.state) addrFields.state.input.value = result.state;
            if (result.postal_code) addrFields.postal_code.input.value = result.postal_code;
            if (result.country) addrFields.country.input.value = result.country;
          } else {
            isGstinVerified = false;
            gstinNotice.className = "alert alert-error";
            gstinNotice.textContent = result.message;
          }
        } catch (err) {
          isGstinVerified = false;
          gstinNotice.className = "alert alert-error";
          gstinNotice.textContent =
            err instanceof Error ? err.message : "GSTIN verification failed.";
        } finally {
          verifyBtn.disabled = false;
          verifyBtn.textContent = "Verify GSTIN";
        }
      });

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Cancel");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);

      const submitBtn = createElement(
        "button",
        "btn btn-primary",
        isEdit ? "Save Changes" : "Create Customer"
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
          company_name: fields.company_name.input.value.trim() || null,
          email: fields.email.input.value.trim() || null,
          phone: fields.phone.input.value.trim() || null,
          tax_id: taxInput.value.trim().toUpperCase() || null,
          gstin_verified: isGstinVerified && Boolean(taxInput.value.trim()),
          address_line1: addrFields.address_line1.input.value.trim() || null,
          address_line2: addrFields.address_line2.input.value.trim() || null,
          city: addrFields.city.input.value.trim() || null,
          state: addrFields.state.input.value.trim() || null,
          postal_code: addrFields.postal_code.input.value.trim() || null,
          country: addrFields.country.input.value.trim() || null,
          notes: addrFields.notes.input.value.trim() || null,
          is_active: addrFields.is_active.input.checked,
        };

        try {
          if (isEdit) {
            await updateCustomer(customer.id, payload);
          } else {
            await createCustomer(payload);
          }
          close();
          await onSaved();
        } catch (err) {
          submitBtn.disabled = false;
          submitBtn.textContent = isEdit ? "Save Changes" : "Create Customer";
          errorSlot.textContent = err instanceof Error ? err.message : "Failed to save customer.";
          errorSlot.classList.remove("is-hidden");
        }
      });

      body.appendChild(form);
    },
  });
}

export function createCustomersController({ onAuthExpired, onCountsChanged }) {
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

      viewState.data = await fetchCustomers({
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
      viewState.error = err instanceof Error ? err.message : "Failed to load customers.";
    }
    render(container);
  }

  function render(container) {
    container.replaceChildren();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(createElement("h2", "section-heading", "Customers"));
    headingWrap.appendChild(
      createElement("p", "section-subtitle", "Manage customer contacts, verified GSTINs, and billing addresses.")
    );
    const addBtn = createElement("button", "btn btn-primary", "+ Add Customer");
    addBtn.type = "button";
    addBtn.addEventListener("click", () => {
      openCustomerModal({
        customer: null,
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
    searchInput.placeholder = "Search name, company, email, phone...";
    searchInput.value = viewState.q;
    searchInput.setAttribute("aria-label", "Search customers");

    const statusSelect = createElement("select", "form-input toolbar-select");
    statusSelect.setAttribute("aria-label", "Filter customers by status");
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
      card.appendChild(createElement("p", "section-subtitle", "Loading customers..."));
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
      empty.appendChild(createElement("h3", "empty-state-title", "No customers found"));
      empty.appendChild(
        createElement(
          "p",
          "empty-state-text",
          viewState.q || viewState.status !== "all"
            ? "No customers match your current search or status filter."
            : "Add your first customer to prepare billing details for invoices."
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
    for (const label of ["Customer", "Contact", "Location / GSTIN", "Status", ""]) {
      headRow.appendChild(createElement("th", "", label));
    }
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = createElement("tbody");
    for (const customer of items) {
      const row = createElement("tr");

      const nameCell = createElement("td");
      nameCell.appendChild(createElement("span", "cell-primary", customer.name));
      if (customer.company_name) {
        nameCell.appendChild(createElement("span", "cell-secondary", customer.company_name));
      }

      const contactCell = createElement("td");
      contactCell.appendChild(createElement("span", "", customer.email || "—"));
      if (customer.phone) {
        contactCell.appendChild(createElement("span", "cell-secondary", customer.phone));
      }

      const locParts = [customer.city, customer.state, customer.country]
        .filter(Boolean)
        .join(", ");
      const locCell = createElement("td");
      locCell.appendChild(createElement("span", "", locParts || "—"));
      if (customer.tax_id) {
        const taxLine = createElement("span", "cell-secondary");
        taxLine.textContent = customer.gstin_verified
          ? `GSTIN: ${customer.tax_id} (Verified)`
          : `Tax ID: ${customer.tax_id}`;
        locCell.appendChild(taxLine);
      }

      const statusCell = createElement("td");
      statusCell.appendChild(
        createElement(
          "span",
          customer.is_active ? "badge badge-active" : "badge badge-inactive",
          customer.is_active ? "Active" : "Inactive"
        )
      );

      const actionCell = createElement("td");
      const actionWrap = createElement("div", "table-actions");
      const editBtn = createElement("button", "btn btn-sm", "Edit");
      editBtn.type = "button";
      editBtn.addEventListener("click", () => {
        openCustomerModal({
          customer,
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
          title: "Delete Customer",
          message: `Delete "${customer.name}"? This action cannot be undone.`,
          onConfirm: async () => {
            await deleteCustomer(customer.id);
            await load(container);
            onCountsChanged();
          },
        });
      });

      actionWrap.appendChild(editBtn);
      actionWrap.appendChild(delBtn);
      actionCell.appendChild(actionWrap);

      row.appendChild(nameCell);
      row.appendChild(contactCell);
      row.appendChild(locCell);
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
