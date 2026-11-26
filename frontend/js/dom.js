/**
 * Shared safe DOM builder and formatting helpers.
 */

export function createElement(tag, className, text) {
  const el = document.createElement(tag);
  if (className) {
    el.className = className;
  }
  if (typeof text === "string") {
    el.textContent = text;
  }
  return el;
}

export function createField({
  id,
  name,
  label,
  type = "text",
  value = "",
  required = false,
  placeholder = "",
  help = "",
  fullWidth = false,
  min,
  max,
  step,
  maxLength,
  autocomplete,
}) {
  const wrapper = createElement("div", fullWidth ? "form-field form-field-full" : "form-field");
  const labelEl = createElement("label", "form-label", label);
  labelEl.setAttribute("for", id);

  const input = createElement("input", "form-input");
  input.id = id;
  input.name = name;
  input.type = type;
  input.value = value ?? "";
  if (required) input.required = true;
  if (placeholder) input.placeholder = placeholder;
  if (typeof min === "number") input.min = String(min);
  if (typeof max === "number") input.max = String(max);
  if (step !== undefined) input.step = String(step);
  if (typeof maxLength === "number") input.maxLength = maxLength;
  if (autocomplete) input.autocomplete = autocomplete;

  wrapper.appendChild(labelEl);
  wrapper.appendChild(input);
  if (help) {
    wrapper.appendChild(createElement("span", "form-help", help));
  }
  return { wrapper, input };
}

export function createCheckboxField({ id, name, label, checked = true, fullWidth = false }) {
  const wrapper = createElement("div", fullWidth ? "form-field form-field-full" : "form-field");
  const row = createElement("label", "checkbox-row");
  row.setAttribute("for", id);

  const input = document.createElement("input");
  input.id = id;
  input.name = name;
  input.type = "checkbox";
  input.checked = Boolean(checked);

  row.appendChild(input);
  row.appendChild(createElement("span", "", label));
  wrapper.appendChild(row);
  return { wrapper, input };
}

export function formatCurrency(amount, currencyCode = "USD") {
  const num = Number(amount);
  if (!Number.isFinite(num)) {
    return `${currencyCode} ${amount}`;
  }
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currencyCode,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(num);
  } catch {
    return `${currencyCode} ${num.toFixed(2)}`;
  }
}

export function renderPaginationBar({ page, totalPages, total, onPageChange }) {
  const bar = createElement("div", "pagination-bar");
  bar.appendChild(
    createElement("span", "", `Page ${page} of ${totalPages} (${total} total)`)
  );

  const controls = createElement("div", "pagination-controls");
  const prevBtn = createElement("button", "btn btn-sm", "Previous");
  prevBtn.type = "button";
  prevBtn.disabled = page <= 1;
  prevBtn.addEventListener("click", () => onPageChange(page - 1));

  const nextBtn = createElement("button", "btn btn-sm", "Next");
  nextBtn.type = "button";
  nextBtn.disabled = page >= totalPages;
  nextBtn.addEventListener("click", () => onPageChange(page + 1));

  controls.appendChild(prevBtn);
  controls.appendChild(nextBtn);
  bar.appendChild(controls);
  return bar;
}

export function showToast(message, variant = "info", durationMs = 4500) {
  const region = document.getElementById("toast-region");
  if (!region || !message) return;

  const toast = createElement("div", `toast toast-${variant}`);
  toast.setAttribute("role", variant === "error" ? "alert" : "status");

  const textEl = createElement("span", "toast-message", message);
  const closeBtn = createElement("button", "toast-close-btn", "×");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "Dismiss notification");

  const dismiss = () => {
    toast.classList.add("is-leaving");
    window.setTimeout(() => toast.remove(), 180);
  };
  closeBtn.addEventListener("click", dismiss);

  toast.appendChild(textEl);
  toast.appendChild(closeBtn);
  region.appendChild(toast);

  if (durationMs > 0) {
    window.setTimeout(dismiss, durationMs);
  }
}
