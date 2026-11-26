/**
 * Accessible modal and confirmation dialog utilities.
 */

import { createElement } from "/js/dom.js";

let activeCleanup = null;

export function closeModal() {
  if (typeof activeCleanup === "function") {
    activeCleanup();
    activeCleanup = null;
  }
}

export function openModal({ title, small = false, renderBody }) {
  closeModal();

  const backdrop = createElement("div", "modal-backdrop");
  backdrop.setAttribute("role", "dialog");
  backdrop.setAttribute("aria-modal", "true");

  const dialog = createElement("div", small ? "modal-dialog modal-dialog-sm" : "modal-dialog");
  const header = createElement("div", "modal-header");
  const heading = createElement("h2", "modal-title", title);
  const closeBtn = createElement("button", "btn btn-icon", "×");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "Close dialog");

  header.appendChild(heading);
  header.appendChild(closeBtn);
  dialog.appendChild(header);

  const body = createElement("div");
  dialog.appendChild(body);
  backdrop.appendChild(dialog);
  document.body.appendChild(backdrop);

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      closeModal();
    }
  };

  closeBtn.addEventListener("click", closeModal);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) {
      closeModal();
    }
  });
  document.addEventListener("keydown", onKeyDown);

  activeCleanup = () => {
    document.removeEventListener("keydown", onKeyDown);
    backdrop.remove();
  };

  renderBody(body, closeModal);
  closeBtn.focus();
}

export function openConfirmDialog({ title, message, confirmLabel = "Delete", onConfirm }) {
  openModal({
    title,
    small: true,
    renderBody: (body, close) => {
      const text = createElement("p", "section-subtitle", message);
      const errorSlot = createElement("div", "alert alert-error is-hidden");
      errorSlot.setAttribute("role", "alert");

      const actions = createElement("div", "form-actions");
      const cancelBtn = createElement("button", "btn", "Cancel");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", close);

      const confirmBtn = createElement("button", "btn btn-danger", confirmLabel);
      confirmBtn.type = "button";
      confirmBtn.addEventListener("click", async () => {
        confirmBtn.disabled = true;
        confirmBtn.textContent = "Deleting...";
        errorSlot.classList.add("is-hidden");
        try {
          await onConfirm();
          close();
        } catch (err) {
          confirmBtn.disabled = false;
          confirmBtn.textContent = confirmLabel;
          errorSlot.textContent = err instanceof Error ? err.message : "Action failed.";
          errorSlot.classList.remove("is-hidden");
        }
      });

      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      body.appendChild(text);
      body.appendChild(errorSlot);
      body.appendChild(actions);
    },
  });
}
