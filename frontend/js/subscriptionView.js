/**
 * Subscription Card, Live Countdown Timer, Feature Limits, and Activation Code UI.
 */

import { activateSubscriptionCode, fetchSubscriptionStatus } from "/js/api.js";
import { createElement, createField, showToast } from "/js/dom.js";
import { openModal } from "/js/modal.js";

function formatDateDisplay(isoValue) {
  if (!isoValue) return "Not Set";
  const dt = new Date(isoValue);
  if (Number.isNaN(dt.getTime())) return String(isoValue);
  return dt.toLocaleDateString(undefined, { day: "2-digit", month: "long", year: "numeric" });
}

function getLiveCountdownParts(sub, syncedAtMs) {
  if (!sub || sub.status !== "ACTIVE" || !sub.expires_at) {
    return { expired: sub?.status === "EXPIRED", days: 0, hours: 0, minutes: 0, seconds: 0 };
  }
  const serverNowMs = new Date(sub.server_now).getTime();
  const expiresMs = new Date(sub.expires_at).getTime();
  const elapsedSinceSync = Date.now() - syncedAtMs;
  const remainingMs = Math.max(0, expiresMs - (serverNowMs + elapsedSinceSync));
  const totalSec = Math.floor(remainingMs / 1000);
  if (totalSec <= 0) {
    return { expired: true, days: 0, hours: 0, minutes: 0, seconds: 0 };
  }
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;
  return { expired: false, days, hours, minutes, seconds };
}

function openContactAdminModal(supportInfo) {
  openModal({
    title: "Contact Administrator for Subscription Renewal",
    small: true,
    renderBody: (body, close) => {
      body.appendChild(
        createElement(
          "p",
          "section-subtitle",
          "Share your registered business email with your administrator to purchase, renew, or receive a new activation code."
        )
      );
      const list = createElement("div", "health-details");
      for (const [k, v] of [
        ["Administrator Email", supportInfo?.support_email || "support@rmstorvix.com"],
        ["Support Phone", supportInfo?.support_phone || "+91-1800-000-0000"],
      ]) {
        const row = createElement("div", "health-row");
        row.appendChild(createElement("span", "health-key", k));
        row.appendChild(createElement("span", "health-val", v));
        list.appendChild(row);
      }
      body.appendChild(list);

      const actions = createElement("div", "form-actions");
      const okBtn = createElement("button", "btn btn-primary", "Close");
      okBtn.type = "button";
      okBtn.addEventListener("click", close);
      actions.appendChild(okBtn);
      body.appendChild(actions);
    },
  });
}

export function buildSubscriptionSummaryCard({
  subscription,
  supportInfo,
  onNavigate,
  compact = false,
}) {
  const card = createElement("section", "card subscription-card");
  const syncedAtMs = Date.now();
  const status = subscription?.status || "NOT_ACTIVATED";

  const head = createElement("div", "card-header");
  const titleWrap = createElement("div");
  titleWrap.appendChild(createElement("p", "metric-label", "SUBSCRIPTION STATUS"));
  const badgeCls =
    status === "ACTIVE"
      ? subscription?.is_expiring_soon
        ? "badge badge-partially_paid"
        : "badge badge-paid"
      : status === "EXPIRED" || status === "SUSPENDED"
      ? "badge badge-overdue"
      : "badge badge-draft";
  const topLine = createElement("div", "sub-card-headline");
  topLine.appendChild(createElement("h3", "card-title", subscription?.plan_name || "No Active Plan"));
  topLine.appendChild(createElement("span", badgeCls, status));
  titleWrap.appendChild(topLine);
  head.appendChild(titleWrap);

  const ctaGroup = createElement("div", "topbar-actions");
  if (typeof onNavigate === "function") {
    const codeBtn = createElement("button", "btn btn-sm btn-primary", "Activate / Renew");
    codeBtn.type = "button";
    codeBtn.addEventListener("click", () => onNavigate("activation"));
    ctaGroup.appendChild(codeBtn);
  }
  const contactBtn = createElement("button", "btn btn-sm", "Contact Admin");
  contactBtn.type = "button";
  contactBtn.addEventListener("click", () => openContactAdminModal(supportInfo));
  ctaGroup.appendChild(contactBtn);
  head.appendChild(ctaGroup);
  card.appendChild(head);

  // Live countdown block
  const countdownEl = createElement("div", "sub-countdown-grid");
  const timerFields = {};
  for (const [key, label] of [
    ["days", "Days Remaining"],
    ["hours", "Hours"],
    ["minutes", "Minutes"],
    ["seconds", "Seconds"],
  ]) {
    const box = createElement("div", "sub-timer-cell");
    const valEl = createElement("span", "sub-timer-num", "0");
    box.appendChild(valEl);
    box.appendChild(createElement("span", "sub-timer-lbl", label));
    countdownEl.appendChild(box);
    timerFields[key] = valEl;
  }

  function refreshTimerDisplay() {
    const parts = getLiveCountdownParts(subscription, syncedAtMs);
    timerFields.days.textContent = String(parts.days);
    timerFields.hours.textContent = String(parts.hours).padStart(2, "0");
    timerFields.minutes.textContent = String(parts.minutes).padStart(2, "0");
    timerFields.seconds.textContent = String(parts.seconds).padStart(2, "0");
  }
  refreshTimerDisplay();
  const intervalId = window.setInterval(() => {
    if (!document.body.contains(card)) {
      window.clearInterval(intervalId);
      return;
    }
    refreshTimerDisplay();
  }, 1000);

  card.appendChild(countdownEl);

  // Progress bar
  const pct = Math.min(100, Math.max(0, Number(subscription?.progress_percent || 0)));
  const progressWrap = createElement("div", "sub-progress-wrap");
  const progressTrack = createElement("div", "sub-progress-track");
  const progressFill = createElement("div", "sub-progress-fill");
  progressFill.style.width = `${pct}%`;
  progressTrack.appendChild(progressFill);
  progressWrap.appendChild(progressTrack);
  progressWrap.appendChild(
    createElement(
      "div",
      "sub-dates-row",
      `Activated: ${formatDateDisplay(subscription?.starts_at)} • Expires on: ${formatDateDisplay(subscription?.expires_at)} (${pct.toFixed(0)}% remaining)`
    )
  );
  card.appendChild(progressWrap);

  if (status === "EXPIRED") {
    card.appendChild(
      createElement(
        "div",
        "alert alert-error",
        `Subscription expired on ${formatDateDisplay(subscription?.expires_at)}. Invoice/record creation is locked; reading & CSV export remain accessible.`
      )
    );
  } else if (subscription?.is_expiring_soon) {
    card.appendChild(
      createElement(
        "div",
        "banner",
        `Renewal notice: Your plan expires in ${subscription.remaining_days} days (${subscription.remaining_hours} hours). Enter an activation code to extend before expiry.`
      )
    );
  }

  if (!compact && subscription?.limits) {
    const lim = subscription.limits;
    const limitsGrid = createElement("div", "metrics-grid");
    for (const [label, used, maxVal] of [
      ["Invoices Quota", lim.invoices_used, lim.max_invoices],
      ["Customers Quota", lim.customers_used, lim.max_customers],
      ["Products Quota", lim.products_used, lim.max_products],
      ["Users Quota", lim.users_used, lim.max_users],
    ]) {
      const box = createElement("article", "card");
      box.appendChild(createElement("p", "metric-label", label));
      box.appendChild(
        createElement("p", "metric-value", maxVal === null ? `${used} / Unlimited` : `${used} / ${maxVal}`)
      );
      limitsGrid.appendChild(box);
    }
    card.appendChild(limitsGrid);
  }

  return card;
}

export function createSubscriptionController({
  getSupportInfo,
  onAuthExpired,
  onSubscriptionUpdated,
  onNavigate,
}) {
  const viewState = {
    loading: false,
    error: null,
    sub: null,
    submittingCode: false,
    codeResult: null,
  };

  async function load(container, mode) {
    viewState.loading = true;
    viewState.error = null;
    render(container, mode);

    try {
      viewState.sub = await fetchSubscriptionStatus();
      onSubscriptionUpdated?.(viewState.sub);
      viewState.loading = false;
    } catch (err) {
      viewState.loading = false;
      if (err?.status === 401) {
        onAuthExpired();
        return;
      }
      viewState.error = err instanceof Error ? err.message : "Failed to load subscription.";
    }
    render(container, mode);
  }

  function render(container, mode) {
    container.replaceChildren();
    const supportInfo = getSupportInfo();

    const header = createElement("div", "section-header");
    const headingWrap = createElement("div");
    headingWrap.appendChild(
      createElement(
        "h2",
        "section-heading",
        mode === "activation" ? "Activate Subscription" : "Subscription & Plan"
      )
    );
    headingWrap.appendChild(
      createElement(
        "p",
        "section-subtitle",
        mode === "activation"
          ? "Redeem your unique RMX-XXXX-XXXX-XXXX activation code to start or extend your plan."
          : "View plan expiration countdown, remaining days/hours, and feature quota usage."
      )
    );
    header.appendChild(headingWrap);
    container.appendChild(header);

    if (viewState.loading && !viewState.sub) {
      const card = createElement("section", "card");
      card.appendChild(createElement("p", "section-subtitle", "Loading subscription details..."));
      container.appendChild(card);
      return;
    }

    if (viewState.error) {
      const alert = createElement("div", "alert alert-error", viewState.error);
      alert.setAttribute("role", "alert");
      container.appendChild(alert);
    }

    if (mode === "activation") {
      const formCard = createElement("section", "card");
      formCard.appendChild(
        createElement("h3", "card-title", "Enter Activation Code")
      );
      formCard.appendChild(
        createElement(
          "p",
          "section-subtitle",
          "Activation codes extend an active subscription or start a fresh period from the redemption timestamp. Pending approval accounts cannot bypass administrator review."
        )
      );

      if (viewState.codeResult) {
        const ok = createElement("div", "alert alert-success", viewState.codeResult);
        ok.setAttribute("role", "status");
        formCard.appendChild(ok);
      }

      const codeForm = createElement("form", "form-stack");
      const codeInput = createField({
        id: "user-activation-code",
        name: "code",
        label: "Activation Code *",
        required: true,
        maxLength: 32,
        placeholder: "RMX-7K9P-4D2M-8Q6T",
        help: "Codes are case-insensitive and formatted as RMX-XXXX-XXXX-XXXX.",
      });
      codeInput.input.style.fontFamily = "var(--font-mono)";
      codeInput.input.style.textTransform = "uppercase";
      codeForm.appendChild(codeInput.wrapper);

      const errSlot = createElement("div", "alert alert-error is-hidden");
      errSlot.setAttribute("role", "alert");
      codeForm.appendChild(errSlot);

      const actions = createElement("div", "form-actions");
      const subBtn = createElement(
        "button",
        "btn btn-primary",
        viewState.submittingCode ? "Validating Code..." : "Activate Code"
      );
      subBtn.type = "submit";
      subBtn.disabled = Boolean(viewState.submittingCode);
      actions.appendChild(subBtn);
      codeForm.appendChild(actions);

      codeForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        viewState.submittingCode = true;
        errSlot.classList.add("is-hidden");
        subBtn.disabled = true;
        subBtn.textContent = "Validating Code...";
        try {
          const updated = await activateSubscriptionCode(codeInput.input.value.trim().toUpperCase());
          viewState.sub = updated;
          viewState.submittingCode = false;
          viewState.codeResult = `Code accepted! "${updated.plan_name}" is active until ${formatDateDisplay(updated.expires_at)}.`;
          onSubscriptionUpdated?.(updated);
          showToast("Subscription updated successfully.", "success");
          render(container, mode);
        } catch (err) {
          viewState.submittingCode = false;
          subBtn.disabled = false;
          subBtn.textContent = "Activate Code";
          errSlot.textContent = err instanceof Error ? err.message : "Failed to activate code.";
          errSlot.classList.remove("is-hidden");
        }
      });

      formCard.appendChild(codeForm);
      container.appendChild(formCard);
    }

    if (viewState.sub) {
      container.appendChild(
        buildSubscriptionSummaryCard({
          subscription: viewState.sub,
          supportInfo,
          onNavigate,
          compact: false,
        })
      );
    }
  }

  return {
    mountSubscription(container) {
      viewState.codeResult = null;
      return load(container, "subscription");
    },
    mountActivation(container) {
      return load(container, "activation");
    },
  };
}
