/**
 * All 10 Administrator Panel Modules (Overview, Approvals, Users, Subscriptions,
 * Activation Codes, Plans, Notifications, SaaS Reports, Audit Logs, Settings).
 */

import {
  activateAdminUser,
  approveAdminUser,
  assignAdminCode,
  assignUserSubscription,
  changeAdminPassword,
  createAdminPlan,
  deactivateAdminUser,
  deleteAdminUser,
  editAdminUserBusiness,
  extendAdminSubscription,
  fetchAdminAuditLogs,
  fetchAdminCodes,
  fetchAdminNotifications,
  fetchAdminOverview,
  fetchAdminPlans,
  fetchAdminSettings,
  fetchAdminSubscriptions,
  fetchAdminUserDetail,
  fetchAdminUsers,
  generateAdminCodes,
  getAdminCodesExportUrl,
  markAdminNotificationRead,
  markAllAdminNotificationsRead,
  reactivateAdminUser,
  redeemAdminCodeForUser,
  rejectAdminUser,
  resetAdminUserPassword,
  revokeAdminCode,
  saveAdminSettings,
  suspendAdminUser,
  updateAdminPlan,
  updateAdminSubscriptionStatus,
} from "/js/adminApi.js";
import { createCheckboxField, createElement, createField, renderPaginationBar, showToast } from "/js/dom.js";
import { openConfirmDialog, openModal } from "/js/modal.js";

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString();
}

function statusBadge(status) {
  const s = String(status || "UNKNOWN").toUpperCase();
  const cls =
    s === "ACTIVE" || s === "AVAILABLE" || s === "APPROVED"
      ? "badge-paid"
      : s === "PENDING_APPROVAL" || s === "ASSIGNED" || s === "ACTIVATED"
      ? "badge-partially_paid"
      : s === "EXPIRED" || s === "SUSPENDED" || s === "REJECTED" || s === "REVOKED" || s === "INACTIVE"
      ? "badge-overdue"
      : "badge-draft";
  return createElement("span", `badge ${cls}`, s.replaceAll("_", " "));
}

function copyText(text) {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(
      () => showToast(`Copied ${text}`, "success", 2200),
      () => showToast(`Code: ${text}`, "info", 3000)
    );
  } else {
    showToast(`Code: ${text}`, "info", 3500);
  }
}

export function createAdminViewsController({ onAuthExpired, onAdminUpdated, onNavigate }) {
  const cache = {
    overview: null,
    plans: [],
    userFilters: { q: "", approval_status: "", subscription_status: "", page: 1 },
    subFilters: { q: "", status: "", expiring_within_days: "", page: 1 },
    codeFilters: { q: "", status: "", page: 1 },
    auditFilters: { action: "", page: 1 },
  };

  function handleError(err, fallback) {
    if (err?.status === 401) {
      onAuthExpired();
      return true;
    }
    showToast(err instanceof Error ? err.message : fallback, "error");
    return false;
  }

  // --- Reusable Modals ---
  function openAssignSubscriptionModal(userRow, onDone) {
    openModal({
      title: `Assign Subscription — ${userRow.business_name}`,
      small: true,
      renderBody: async (body, close) => {
        if (cache.plans.length === 0) {
          cache.plans = await fetchAdminPlans(true).catch(() => []);
        }
        const form = createElement("form", "form-stack");
        const errBox = createElement("div", "alert alert-error is-hidden");

        const planWrap = createElement("div", "form-field");
        const planLbl = createElement("label", "form-label", "Select Plan Template (Optional)");
        const planSel = createElement("select", "form-input");
        const customOpt = createElement("option", "", "Custom Plan Duration");
        customOpt.value = "";
        planSel.appendChild(customOpt);
        for (const p of cache.plans.filter((x) => x.status === "ACTIVE")) {
          const opt = createElement("option", "", `${p.name} (${p.duration_days} days)`);
          opt.value = String(p.id);
          planSel.appendChild(opt);
        }
        planWrap.appendChild(planLbl);
        planWrap.appendChild(planSel);

        const durField = createField({
          id: "adm-assign-days",
          name: "duration_days",
          label: "Duration Days *",
          type: "number",
          value: "30",
          required: true,
        });
        planSel.addEventListener("change", () => {
          const matched = cache.plans.find((x) => String(x.id) === planSel.value);
          if (matched) durField.input.value = String(matched.duration_days);
        });

        const notesField = createField({
          id: "adm-assign-notes",
          name: "notes",
          label: "Notes (Optional)",
          maxLength: 300,
          placeholder: "Manual offline payment verified",
        });
        const actCheck = createCheckboxField({
          id: "adm-assign-activate",
          name: "activate_user",
          label: "Also activate user approval status immediately",
          checked: true,
        });

        const actions = createElement("div", "form-actions");
        const cancelBtn = createElement("button", "btn", "Cancel");
        cancelBtn.type = "button";
        cancelBtn.addEventListener("click", close);
        const saveBtn = createElement("button", "btn btn-primary", "Assign Subscription");
        saveBtn.type = "submit";
        actions.appendChild(cancelBtn);
        actions.appendChild(saveBtn);

        form.appendChild(errBox);
        form.appendChild(planWrap);
        form.appendChild(durField.wrapper);
        form.appendChild(notesField.wrapper);
        form.appendChild(actCheck.wrapper);
        form.appendChild(actions);

        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          saveBtn.disabled = true;
          errBox.classList.add("is-hidden");
          try {
            await assignUserSubscription(userRow.id, {
              plan_id: planSel.value ? Number(planSel.value) : null,
              duration_days: Number(durField.input.value),
              activate_user: actCheck.input.checked,
              notes: notesField.input.value.trim() || null,
            });
            showToast("Subscription assigned and activated.", "success");
            close();
            await onDone();
          } catch (err) {
            saveBtn.disabled = false;
            errBox.textContent = err instanceof Error ? err.message : "Failed to assign plan.";
            errBox.classList.remove("is-hidden");
          }
        });
        body.appendChild(form);
      },
    });
  }

  function openUserDetailModal(userId, onDone) {
    openModal({
      title: "User & Business Account Details",
      renderBody: async (body, close) => {
        body.appendChild(createElement("p", "section-subtitle", "Loading details..."));
        try {
          const detail = await fetchAdminUserDetail(userId);
          body.replaceChildren();
          const u = detail.user;

          const grid = createElement("div", "health-details");
          for (const [k, v] of [
            ["Owner", u.full_name],
            ["Email", u.email],
            ["Mobile", u.phone || "—"],
            ["Business Name", u.business_name],
            ["Business Type", u.business_type || "—"],
            ["GSTIN", u.business_gstin || "—"],
            ["Address", u.business_address || "—"],
            ["Approval Status", u.approval_status],
            ["Self-Activation Allowed", u.allow_self_activation ? "Yes" : "No"],
            ["Subscription", `${u.subscription_status} (${u.subscription_plan_name || "None"})`],
            ["Expires At", fmtDateTime(u.subscription_expires_at)],
            ["Remaining Days", String(u.subscription_remaining_days)],
          ]) {
            const row = createElement("div", "health-row");
            row.appendChild(createElement("span", "health-key", k));
            row.appendChild(createElement("span", "health-val", v));
            grid.appendChild(row);
          }
          body.appendChild(grid);

          // Assigned codes
          body.appendChild(createElement("h4", "card-title", "Assigned Activation Codes"));
          if (detail.assigned_codes.length === 0) {
            body.appendChild(createElement("p", "section-subtitle", "No codes assigned."));
          } else {
            const list = createElement("div", "history-list");
            for (const c of detail.assigned_codes) {
              const row = createElement("div", "history-item");
              row.appendChild(createElement("span", "admin-code-chip", `${c.code_value} (${c.duration_days}d)`));
              row.appendChild(statusBadge(c.status));
              list.appendChild(row);
            }
            body.appendChild(list);
          }

          // Approval history
          body.appendChild(createElement("h4", "card-title", "Approval Audit Trail"));
          if (detail.approval_history.length === 0) {
            body.appendChild(createElement("p", "section-subtitle", "No approval events yet."));
          } else {
            const list = createElement("div", "history-list");
            for (const h of detail.approval_history.slice(0, 8)) {
              const item = createElement("div", "history-item");
              item.appendChild(
                createElement(
                  "strong",
                  "",
                  `${h.previous_status || "NEW"} → ${h.new_status}${h.reason ? ` (${h.reason})` : ""}`
                )
              );
              item.appendChild(createElement("p", "history-item-meta", fmtDateTime(h.created_at)));
              list.appendChild(item);
            }
            body.appendChild(list);
          }

          // Subscription history
          body.appendChild(createElement("h4", "card-title", "Subscription History"));
          if (!detail.subscription_history || detail.subscription_history.length === 0) {
            body.appendChild(createElement("p", "section-subtitle", "No subscription history yet."));
          } else {
            const slist = createElement("div", "history-list");
            for (const sh of detail.subscription_history.slice(0, 8)) {
              const item = createElement("div", "history-item");
              item.appendChild(
                createElement(
                  "strong",
                  "",
                  `${sh.action} (${sh.previous_status || "NONE"} → ${sh.new_status})`
                )
              );
              item.appendChild(
                createElement(
                  "p",
                  "history-item-meta",
                  `${sh.actor_type.toUpperCase()} • ${fmtDateTime(sh.created_at)}${sh.new_expires_at ? ` • Expires ${fmtDate(sh.new_expires_at)}` : ""}`
                )
              );
              slist.appendChild(item);
            }
            body.appendChild(slist);
          }

          const actions = createElement("div", "form-actions");
          const subBtn = createElement("button", "btn btn-primary", "Assign / Activate Plan");
          subBtn.type = "button";
          subBtn.addEventListener("click", () => {
            close();
            openAssignSubscriptionModal(u, onDone);
          });
          const closeBtn = createElement("button", "btn", "Close");
          closeBtn.type = "button";
          closeBtn.addEventListener("click", close);
          actions.appendChild(subBtn);
          actions.appendChild(closeBtn);
          body.appendChild(actions);
        } catch (err) {
          handleError(err, "Failed to load user details.");
          close();
        }
      },
    });
  }

  function openEditUserModal(userRow, onDone) {
    openModal({
      title: `Edit Business — ${userRow.business_name}`,
      renderBody: (body, close) => {
        const form = createElement("form", "form-stack");
        const errBox = createElement("div", "alert alert-error is-hidden");
        const ownerField = createField({ id: "ed-owner", name: "full_name", label: "Owner Name", value: userRow.full_name });
        const phoneField = createField({ id: "ed-phone", name: "phone", label: "Mobile", value: userRow.phone || "" });
        const bizField = createField({ id: "ed-biz", name: "business_name", label: "Business Name", value: userRow.business_name });
        const typeField = createField({ id: "ed-type", name: "business_type", label: "Business Type", value: userRow.business_type || "" });
        const gstField = createField({ id: "ed-gst", name: "tax_id", label: "GSTIN", value: userRow.business_gstin || "" });
        const selfAct = createCheckboxField({
          id: "ed-self",
          name: "allow_self_activation",
          label: "Allow user self-activation via code",
          checked: Boolean(userRow.allow_self_activation),
        });
        const actions = createElement("div", "form-actions");
        const cancel = createElement("button", "btn", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", close);
        const save = createElement("button", "btn btn-primary", "Save Changes");
        save.type = "submit";
        actions.appendChild(cancel);
        actions.appendChild(save);

        form.append(errBox, ownerField.wrapper, phoneField.wrapper, bizField.wrapper, typeField.wrapper, gstField.wrapper, selfAct.wrapper, actions);
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          save.disabled = true;
          try {
            await editAdminUserBusiness(userRow.id, {
              full_name: ownerField.input.value.trim(),
              phone: phoneField.input.value.trim() || null,
              business_name: bizField.input.value.trim(),
              business_type: typeField.input.value.trim() || null,
              tax_id: gstField.input.value.trim() || null,
              allow_self_activation: selfAct.input.checked,
            });
            showToast("User and business updated.", "success");
            close();
            await onDone();
          } catch (err) {
            save.disabled = false;
            errBox.textContent = err instanceof Error ? err.message : "Update failed.";
            errBox.classList.remove("is-hidden");
          }
        });
        body.appendChild(form);
      },
    });
  }

  function openResetPasswordModal(userRow, onDone) {
    openModal({
      title: `Reset Password — ${userRow.email}`,
      small: true,
      renderBody: (body, close) => {
        const form = createElement("form", "form-stack");
        const errBox = createElement("div", "alert alert-error is-hidden");
        const pwd = createField({
          id: "adm-rst-pwd",
          name: "new_password",
          label: "New Temporary Password *",
          type: "password",
          required: true,
          help: "Minimum 8 characters.",
        });
        const reqChange = createCheckboxField({
          id: "adm-rst-chg",
          name: "require_password_change",
          label: "Flag user account for password update",
          checked: true,
        });
        const actions = createElement("div", "form-actions");
        const cancel = createElement("button", "btn", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", close);
        const save = createElement("button", "btn btn-primary", "Reset Password");
        save.type = "submit";
        actions.append(cancel, save);

        form.append(errBox, pwd.wrapper, reqChange.wrapper, actions);
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          save.disabled = true;
          try {
            await resetAdminUserPassword(userRow.id, {
              new_password: pwd.input.value,
              require_password_change: reqChange.input.checked,
            });
            showToast("User password reset and sessions revoked.", "success");
            close();
            await onDone();
          } catch (err) {
            save.disabled = false;
            errBox.textContent = err instanceof Error ? err.message : "Reset failed.";
            errBox.classList.remove("is-hidden");
          }
        });
        body.appendChild(form);
      },
    });
  }

  // --- Section Renderers ---
  async function renderOverview(container, isReports = false) {
    container.replaceChildren();
    container.appendChild(createElement("p", "section-subtitle", "Loading platform metrics..."));
    try {
      const [stats, expiringSubs, pendingUsers] = await Promise.all([
        fetchAdminOverview(),
        fetchAdminSubscriptions({ expiring_within_days: 7, page_size: 10 }),
        fetchAdminUsers({ approval_status: "PENDING_APPROVAL", page_size: 6 }),
      ]);
      cache.overview = stats;
      container.replaceChildren();

      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", isReports ? "SaaS Analytics & Reports" : "Platform Overview"));
      hw.appendChild(createElement("p", "section-subtitle", "Live business tenants, approval pipeline, subscription health, and code conversion."));
      hdr.appendChild(hw);
      if (isReports) {
        const csvLink = createElement("a", "btn btn-primary", "Export Activation Codes CSV");
        csvLink.href = getAdminCodesExportUrl();
        hdr.appendChild(csvLink);
      }
      container.appendChild(hdr);

      const kpis = createElement("div", "admin-kpi-grid");
      for (const [label, value, helper] of [
        ["Total Registered Users", stats.total_registered_users, "Business owner accounts"],
        ["Active Users", stats.active_users, "Approved & unlocked workspaces"],
        ["Pending Approvals", stats.pending_approval_users, "Awaiting administrator review"],
        ["Active Subscriptions", stats.active_subscriptions, `${stats.expiring_soon_subscriptions} expiring ≤ 7d`],
        ["Expired Subscriptions", stats.expired_subscriptions, "Write access paused"],
        ["Suspended / Rejected", `${stats.suspended_users} / ${stats.rejected_users}`, `${stats.deactivated_users} deactivated`],
        ["Activation Codes", stats.total_activation_codes, `${stats.available_activation_codes} available • ${stats.used_activation_codes} used`],
        ["Admin Audit Events", stats.recent_audit_count, "Immutable security logs"],
      ]) {
        const card = createElement("article", "admin-kpi-card");
        card.appendChild(createElement("p", "metric-label", label));
        card.appendChild(createElement("p", "metric-value", String(value)));
        card.appendChild(createElement("p", "metric-helper", helper));
        kpis.appendChild(card);
      }
      container.appendChild(kpis);

      // Charts grid
      const charts = createElement("div", "admin-charts-grid");

      const regCard = createElement("section", "card");
      regCard.appendChild(createElement("h3", "card-title", "Monthly Business Registrations"));
      const maxReg = Math.max(1, ...(stats.monthly_registrations || []).map((m) => m.count));
      const regBars = createElement("div", "admin-chart-bars");
      if ((stats.monthly_registrations || []).length === 0) {
        regBars.appendChild(createElement("p", "section-subtitle", "No registration data yet."));
      } else {
        for (const m of stats.monthly_registrations) {
          const row = createElement("div", "admin-chart-row");
          row.appendChild(createElement("span", "cell-secondary", m.month));
          const track = createElement("div", "admin-chart-track");
          const fill = createElement("div", "admin-chart-fill");
          fill.style.width = `${Math.round((m.count / maxReg) * 100)}%`;
          track.appendChild(fill);
          row.appendChild(track);
          row.appendChild(createElement("strong", "cell-numeric", String(m.count)));
          regBars.appendChild(row);
        }
      }
      regCard.appendChild(regBars);
      charts.appendChild(regCard);

      const subCard = createElement("section", "card");
      subCard.appendChild(createElement("h3", "card-title", "Subscription Status Breakdown"));
      const totalSubCount = Math.max(
        1,
        (stats.subscription_breakdown || []).reduce((acc, s) => acc + s.count, 0)
      );
      const subBars = createElement("div", "admin-chart-bars");
      for (const item of stats.subscription_breakdown || []) {
        const row = createElement("div", "admin-chart-row");
        row.appendChild(createElement("span", "cell-secondary", item.status.replaceAll("_", " ")));
        const track = createElement("div", "admin-chart-track");
        const fill = createElement("div", "admin-chart-fill");
        fill.style.width = `${Math.round((item.count / totalSubCount) * 100)}%`;
        track.appendChild(fill);
        row.appendChild(track);
        row.appendChild(createElement("strong", "cell-numeric", String(item.count)));
        subBars.appendChild(row);
      }
      subCard.appendChild(subBars);
      charts.appendChild(subCard);
      container.appendChild(charts);

      // Actionable widgets: Pending Approvals + Expiring Soon
      const bottomGrid = createElement("div", "admin-charts-grid");
      const pendCard = createElement("section", "card");
      const pendHead = createElement("div", "card-header");
      pendHead.appendChild(createElement("h3", "card-title", "Pending Approval Queue"));
      const pendBtn = createElement("button", "btn btn-sm", "Open Queue");
      pendBtn.type = "button";
      pendBtn.addEventListener("click", () => onNavigate("approvals"));
      pendHead.appendChild(pendBtn);
      pendCard.appendChild(pendHead);
      if (pendingUsers.items.length === 0) {
        pendCard.appendChild(createElement("p", "section-subtitle", "No pending registration requests."));
      } else {
        const list = createElement("div", "history-list");
        for (const u of pendingUsers.items) {
          const item = createElement("div", "history-item");
          item.appendChild(createElement("strong", "", `${u.business_name} (${u.email})`));
          item.appendChild(createElement("p", "history-item-meta", `Owner: ${u.full_name} • Registered ${fmtDate(u.created_at)}`));
          list.appendChild(item);
        }
        pendCard.appendChild(list);
      }
      bottomGrid.appendChild(pendCard);

      const expCard = createElement("section", "card");
      expCard.appendChild(createElement("h3", "card-title", "Expiring Within 7 Days"));
      if (expiringSubs.items.length === 0) {
        expCard.appendChild(createElement("p", "section-subtitle", "No subscriptions expiring in the next 7 days."));
      } else {
        const list = createElement("div", "history-list");
        for (const s of expiringSubs.items) {
          const item = createElement("div", "history-item");
          item.appendChild(createElement("strong", "", `${s.business_name} — ${s.plan_name}`));
          item.appendChild(createElement("p", "history-item-meta", `${s.remaining_days} days left • Expires ${fmtDate(s.expires_at)}`));
          list.appendChild(item);
        }
        expCard.appendChild(list);
      }
      bottomGrid.appendChild(expCard);
      container.appendChild(bottomGrid);
    } catch (err) {
      handleError(err, "Failed to load admin overview.");
    }
  }

  async function renderUsers(container, pendingOnly = false) {
    container.replaceChildren();
    container.appendChild(createElement("p", "section-subtitle", "Loading business accounts..."));
    try {
      const filters = pendingOnly
        ? { q: cache.userFilters.q, approval_status: "PENDING_APPROVAL", page: 1, page_size: 30 }
        : { ...cache.userFilters, page_size: 20 };
      const data = await fetchAdminUsers(filters);
      container.replaceChildren();

      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", pendingOnly ? "Pending User Approvals" : "User & Business Management"));
      hw.appendChild(createElement("p", "section-subtitle", `${data.total} business account(s) matched.`));
      hdr.appendChild(hw);
      container.appendChild(hdr);

      if (!pendingOnly) {
        const toolbar = createElement("div", "card admin-toolbar-row");
        const fg = createElement("div", "admin-filter-group");
        const qField = createField({ id: "u-q", name: "q", label: "Search", value: cache.userFilters.q, placeholder: "Email, owner, business..." });
        const appSelWrap = createElement("div", "form-field");
        appSelWrap.appendChild(createElement("label", "form-label", "Approval Status"));
        const appSel = createElement("select", "form-input");
        for (const val of ["", "PENDING_APPROVAL", "APPROVED", "ACTIVE", "INACTIVE", "SUSPENDED", "REJECTED"]) {
          const opt = createElement("option", "", val || "All");
          opt.value = val;
          appSel.appendChild(opt);
        }
        appSel.value = cache.userFilters.approval_status;
        appSelWrap.appendChild(appSel);

        const applyBtn = createElement("button", "btn btn-primary", "Filter");
        applyBtn.type = "button";
        applyBtn.addEventListener("click", () => {
          cache.userFilters.q = qField.input.value.trim();
          cache.userFilters.approval_status = appSel.value;
          cache.userFilters.page = 1;
          void renderUsers(container, false);
        });
        fg.append(qField.wrapper, appSelWrap, applyBtn);
        toolbar.appendChild(fg);
        container.appendChild(toolbar);
      }

      const card = createElement("section", "card");
      if (data.items.length === 0) {
        card.appendChild(createElement("p", "section-subtitle", pendingOnly ? "No pending approvals right now." : "No matching users found."));
        container.appendChild(card);
        return;
      }

      const scroll = createElement("div", "table-scroll");
      const table = createElement("table", "data-table");
      const thead = createElement("thead");
      const hr = createElement("tr");
      for (const h of ["Business & Owner", "Contact", "Approval", "Subscription", "Actions"]) {
        hr.appendChild(createElement("th", "", h));
      }
      thead.appendChild(hr);
      table.appendChild(thead);

      const tbody = createElement("tbody");
      for (const u of data.items) {
        const tr = createElement("tr");

        const tdBiz = createElement("td");
        tdBiz.appendChild(createElement("strong", "", u.business_name));
        tdBiz.appendChild(createElement("div", "cell-secondary", `${u.full_name} • ${u.business_type || "General"}`));
        tr.appendChild(tdBiz);

        const tdContact = createElement("td");
        tdContact.appendChild(createElement("div", "", u.email));
        tdContact.appendChild(createElement("div", "cell-secondary", u.phone || "No mobile"));
        tr.appendChild(tdContact);

        const tdApp = createElement("td");
        tdApp.appendChild(statusBadge(u.approval_status));
        tr.appendChild(tdApp);

        const tdSub = createElement("td");
        tdSub.appendChild(statusBadge(u.subscription_status));
        tdSub.appendChild(
          createElement(
            "div",
            "cell-secondary",
            u.subscription_expires_at ? `${u.subscription_remaining_days}d left (${fmtDate(u.subscription_expires_at)})` : "Not activated"
          )
        );
        tr.appendChild(tdSub);

        const tdAct = createElement("td");
        const cluster = createElement("div", "admin-action-cluster");
        const reload = () => renderUsers(container, pendingOnly);

        const viewBtn = createElement("button", "btn btn-sm", "Details");
        viewBtn.type = "button";
        viewBtn.addEventListener("click", () => openUserDetailModal(u.id, reload));
        cluster.appendChild(viewBtn);

        if (u.approval_status === "PENDING_APPROVAL") {
          const appBtn = createElement("button", "btn btn-sm btn-primary", "Approve");
          appBtn.type = "button";
          appBtn.addEventListener("click", async () => {
            await approveAdminUser(u.id, { allow_self_activation: true });
            showToast(`Approved ${u.business_name}.`, "success");
            await reload();
          });
          const rejBtn = createElement("button", "btn btn-sm btn-danger", "Reject");
          rejBtn.type = "button";
          rejBtn.addEventListener("click", () => {
            openConfirmDialog({
              title: "Reject User Registration",
              message: `Reject account "${u.email}" for ${u.business_name}?`,
              confirmLabel: "Reject Account",
              danger: true,
              onConfirm: async () => {
                await rejectAdminUser(u.id, { reason: "Rejected by administrator" });
                showToast(`Rejected ${u.email}.`, "info");
                await reload();
              },
            });
          });
          cluster.append(appBtn, rejBtn);
        }

        if (u.approval_status === "APPROVED" || u.approval_status === "PENDING_APPROVAL") {
          const actBtn = createElement("button", "btn btn-sm btn-primary", "Activate + Plan");
          actBtn.type = "button";
          actBtn.addEventListener("click", () => openAssignSubscriptionModal(u, reload));
          cluster.appendChild(actBtn);
        }

        if (u.approval_status === "ACTIVE") {
          const planBtn = createElement("button", "btn btn-sm", "Assign Plan");
          planBtn.type = "button";
          planBtn.addEventListener("click", () => openAssignSubscriptionModal(u, reload));
          const deactBtn = createElement("button", "btn btn-sm", "Deactivate");
          deactBtn.type = "button";
          deactBtn.addEventListener("click", async () => {
            await deactivateAdminUser(u.id, { reason: "Deactivated by administrator" });
            showToast("User deactivated.", "info");
            await reload();
          });
          const suspBtn = createElement("button", "btn btn-sm btn-danger", "Suspend");
          suspBtn.type = "button";
          suspBtn.addEventListener("click", async () => {
            await suspendAdminUser(u.id, { reason: "Suspended by administrator" });
            showToast("User suspended.", "info");
            await reload();
          });
          cluster.append(planBtn, deactBtn, suspBtn);
        } else if (u.approval_status === "INACTIVE" || u.approval_status === "SUSPENDED" || u.approval_status === "REJECTED") {
          const reactBtn = createElement("button", "btn btn-sm btn-primary", "Reactivate");
          reactBtn.type = "button";
          reactBtn.addEventListener("click", async () => {
            await reactivateAdminUser(u.id, {});
            showToast("User reactivated.", "success");
            await reload();
          });
          cluster.appendChild(reactBtn);
        }

        if (!pendingOnly) {
          const editBtn = createElement("button", "btn btn-sm", "Edit");
          editBtn.type = "button";
          editBtn.addEventListener("click", () => openEditUserModal(u, reload));
          const rstBtn = createElement("button", "btn btn-sm", "Reset Pwd");
          rstBtn.type = "button";
          rstBtn.addEventListener("click", () => openResetPasswordModal(u, reload));
          const delBtn = createElement("button", "btn btn-sm btn-danger", "Delete");
          delBtn.type = "button";
          delBtn.addEventListener("click", () => {
            openConfirmDialog({
              title: "Permanently Delete User",
              message: `Delete user "${u.email}"? (Note: accounts with recorded invoices are safeguarded by accounting rules.)`,
              confirmLabel: "Delete User",
              danger: true,
              onConfirm: async () => {
                try {
                  await deleteAdminUser(u.id);
                  showToast("User deleted.", "success");
                  await reload();
                } catch (err) {
                  handleError(err, "Cannot delete user.");
                }
              },
            });
          });
          cluster.append(editBtn, rstBtn, delBtn);
        }

        tdAct.appendChild(cluster);
        tr.appendChild(tdAct);
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      scroll.appendChild(table);
      card.appendChild(scroll);
      container.appendChild(card);
      if (!pendingOnly) {
        container.appendChild(
          renderPaginationBar({
            page: data.page,
            totalPages: data.total_pages,
            total: data.total,
            onPageChange: (nextPage) => {
              cache.userFilters.page = nextPage;
              void renderUsers(container, false);
            },
          })
        );
      }
    } catch (err) {
      handleError(err, "Failed to load users.");
    }
  }

  async function renderSubscriptions(container) {
    container.replaceChildren();
    container.appendChild(createElement("p", "section-subtitle", "Loading subscriptions..."));
    try {
      const data = await fetchAdminSubscriptions({ ...cache.subFilters, page_size: 25 });
      container.replaceChildren();

      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", "Subscription Management"));
      hw.appendChild(createElement("p", "section-subtitle", `${data.total} business subscription(s).`));
      hdr.appendChild(hw);
      container.appendChild(hdr);

      const toolbar = createElement("div", "card admin-toolbar-row");
      const fg = createElement("div", "admin-filter-group");
      const qField = createField({ id: "sub-q", name: "q", label: "Search", value: cache.subFilters.q, placeholder: "Business or email..." });
      const stWrap = createElement("div", "form-field");
      stWrap.appendChild(createElement("label", "form-label", "Status"));
      const stSel = createElement("select", "form-input");
      for (const val of ["", "ACTIVE", "EXPIRED", "NOT_ACTIVATED", "SUSPENDED", "CANCELLED"]) {
        const opt = createElement("option", "", val || "All");
        opt.value = val;
        stSel.appendChild(opt);
      }
      stSel.value = cache.subFilters.status;
      stWrap.appendChild(stSel);

      const expWrap = createElement("div", "form-field");
      expWrap.appendChild(createElement("label", "form-label", "Expiring Soon"));
      const expSel = createElement("select", "form-input");
      for (const [val, lbl] of [["", "Any"], ["7", "Within 7 days"], ["15", "Within 15 days"], ["30", "Within 30 days"]]) {
        const opt = createElement("option", "", lbl);
        opt.value = val;
        expSel.appendChild(opt);
      }
      expSel.value = cache.subFilters.expiring_within_days;
      expWrap.appendChild(expSel);

      const filterBtn = createElement("button", "btn btn-primary", "Filter");
      filterBtn.type = "button";
      filterBtn.addEventListener("click", () => {
        cache.subFilters.q = qField.input.value.trim();
        cache.subFilters.status = stSel.value;
        cache.subFilters.expiring_within_days = expSel.value;
        void renderSubscriptions(container);
      });
      fg.append(qField.wrapper, stWrap, expWrap, filterBtn);
      toolbar.appendChild(fg);
      container.appendChild(toolbar);

      const card = createElement("section", "card");
      const scroll = createElement("div", "table-scroll");
      const table = createElement("table", "data-table");
      const thead = createElement("thead");
      const hr = createElement("tr");
      for (const h of ["Business", "Plan", "Status", "Dates", "Remaining", "Actions"]) {
        hr.appendChild(createElement("th", "", h));
      }
      thead.appendChild(hr);
      table.appendChild(thead);

      const tbody = createElement("tbody");
      for (const s of data.items) {
        const tr = createElement("tr");
        const tdB = createElement("td");
        tdB.appendChild(createElement("strong", "", s.business_name));
        tdB.appendChild(createElement("div", "cell-secondary", s.owner_email || "—"));
        tr.appendChild(tdB);

        tr.appendChild(createElement("td", "", s.plan_name));
        const tdS = createElement("td");
        tdS.appendChild(statusBadge(s.status));
        tr.appendChild(tdS);

        const tdD = createElement("td");
        tdD.appendChild(createElement("div", "", `Start: ${fmtDate(s.starts_at)}`));
        tdD.appendChild(createElement("div", "cell-secondary", `End: ${fmtDate(s.expires_at)}`));
        tr.appendChild(tdD);

        tr.appendChild(createElement("td", "cell-numeric", `${s.remaining_days} days`));

        const tdA = createElement("td");
        const cluster = createElement("div", "admin-action-cluster");
        for (const extraDays of [30, 90]) {
          const extBtn = createElement("button", "btn btn-sm btn-primary", `+${extraDays}d`);
          extBtn.type = "button";
          extBtn.addEventListener("click", async () => {
            await extendAdminSubscription(s.id, { extra_days: extraDays, notes: `Extended +${extraDays} days` });
            showToast(`Extended "${s.business_name}" by ${extraDays} days.`, "success");
            await renderSubscriptions(container);
          });
          cluster.appendChild(extBtn);
        }
        const stToggle = createElement("button", "btn btn-sm btn-danger", s.status === "ACTIVE" ? "Suspend" : "Set Active");
        stToggle.type = "button";
        stToggle.addEventListener("click", async () => {
          const nextSt = s.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE";
          await updateAdminSubscriptionStatus(s.id, { status: nextSt });
          showToast(`Subscription marked ${nextSt}.`, "info");
          await renderSubscriptions(container);
        });
        cluster.appendChild(stToggle);
        tdA.appendChild(cluster);
        tr.appendChild(tdA);
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      scroll.appendChild(table);
      card.appendChild(scroll);
      container.appendChild(card);
      container.appendChild(
        renderPaginationBar({
          page: data.page,
          totalPages: data.total_pages,
          total: data.total,
          onPageChange: (nextPage) => {
            cache.subFilters.page = nextPage;
            void renderSubscriptions(container);
          },
        })
      );
    } catch (err) {
      handleError(err, "Failed to load subscriptions.");
    }
  }

  async function renderCodes(container) {
    container.replaceChildren();
    container.appendChild(createElement("p", "section-subtitle", "Loading activation codes..."));
    try {
      const [codesRes, plansRes, usersRes] = await Promise.all([
        fetchAdminCodes({ ...cache.codeFilters, page_size: 30 }),
        fetchAdminPlans(false),
        fetchAdminUsers({ page_size: 100 }),
      ]);
      cache.plans = plansRes;
      container.replaceChildren();

      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", "Activation Code Generator"));
      hw.appendChild(createElement("p", "section-subtitle", "Generate single or batch RMX-XXXX-XXXX-XXXX codes, assign to accounts, redeem, or revoke."));
      hdr.appendChild(hw);
      const exportBtn = createElement("a", "btn", "Export CSV");
      exportBtn.href = getAdminCodesExportUrl(cache.codeFilters.status);
      hdr.appendChild(exportBtn);
      container.appendChild(hdr);

      // Generator card
      const genCard = createElement("section", "card");
      genCard.appendChild(createElement("h3", "card-title", "Generate New Activation Codes"));
      const genForm = createElement("form", "form-grid");
      const cntField = createField({ id: "cg-count", name: "count", label: "Quantity (1-50)", type: "number", value: "1", required: true });
      const durField = createField({ id: "cg-days", name: "duration_days", label: "Duration Days", type: "number", value: "30", required: true });

      const planWrap = createElement("div", "form-field");
      planWrap.appendChild(createElement("label", "form-label", "Link Plan (Optional)"));
      const planSel = createElement("select", "form-input");
      planSel.appendChild(createElement("option", "", "None / Standard")).value = "";
      for (const p of plansRes) {
        const opt = createElement("option", "", `${p.name} (${p.duration_days}d)`);
        opt.value = String(p.id);
        planSel.appendChild(opt);
      }
      planSel.addEventListener("change", () => {
        const m = plansRes.find((x) => String(x.id) === planSel.value);
        if (m) durField.input.value = String(m.duration_days);
      });
      planWrap.appendChild(planSel);

      const usrWrap = createElement("div", "form-field");
      usrWrap.appendChild(createElement("label", "form-label", "Assign to User (Optional)"));
      const usrSel = createElement("select", "form-input");
      usrSel.appendChild(createElement("option", "", "Unassigned (Available)")).value = "";
      for (const u of usersRes.items) {
        const opt = createElement("option", "", `${u.business_name} (${u.email})`);
        opt.value = String(u.id);
        usrSel.appendChild(opt);
      }
      usrWrap.appendChild(usrSel);

      const expField = createField({ id: "cg-exp", name: "code_expires_in_days", label: "Code Expiry Days (Optional)", type: "number", placeholder: "e.g. 90" });
      const notesField = createField({ id: "cg-notes", name: "notes", label: "Notes (Optional)", maxLength: 300, placeholder: "Batch / client note" });

      genForm.append(cntField.wrapper, durField.wrapper, planWrap, usrWrap, expField.wrapper, notesField.wrapper);
      const presetRow = createElement("div", "admin-action-cluster");
      for (const d of [7, 30, 90, 180, 365]) {
        const pb = createElement("button", "btn btn-sm", `${d} Days`);
        pb.type = "button";
        pb.addEventListener("click", () => { durField.input.value = String(d); });
        presetRow.appendChild(pb);
      }
      const genBtn = createElement("button", "btn btn-primary", "Generate Code(s)");
      genBtn.type = "submit";
      genBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        genBtn.disabled = true;
        try {
          const created = await generateAdminCodes({
            count: Number(cntField.input.value || 1),
            duration_days: Number(durField.input.value || 30),
            plan_id: planSel.value ? Number(planSel.value) : null,
            assigned_user_id: usrSel.value ? Number(usrSel.value) : null,
            code_expires_in_days: expField.input.value ? Number(expField.input.value) : null,
            notes: notesField.input.value.trim() || null,
          });
          showToast(`Generated ${created.length} code(s): ${created[0]?.code_value}`, "success");
          await renderCodes(container);
        } catch (err) {
          genBtn.disabled = false;
          handleError(err, "Code generation failed.");
        }
      });

      const genFoot = createElement("div", "form-actions");
      genFoot.append(presetRow, genBtn);
      genCard.append(genForm, genFoot);
      container.appendChild(genCard);

      // Table
      const listCard = createElement("section", "card");
      const scroll = createElement("div", "table-scroll");
      const table = createElement("table", "data-table");
      const thead = createElement("thead");
      const hr = createElement("tr");
      for (const h of ["Activation Code", "Duration & Plan", "Status", "Assigned To", "Usage / Created", "Actions"]) {
        hr.appendChild(createElement("th", "", h));
      }
      thead.appendChild(hr);
      table.appendChild(thead);

      const tbody = createElement("tbody");
      for (const c of codesRes.items) {
        const tr = createElement("tr");
        const tdC = createElement("td");
        const chip = createElement("button", "admin-code-chip", c.code_value);
        chip.type = "button";
        chip.title = "Click to copy code";
        chip.addEventListener("click", () => copyText(c.code_value));
        tdC.appendChild(chip);
        tr.appendChild(tdC);

        tr.appendChild(createElement("td", "", `${c.duration_days} days${c.plan_name ? ` • ${c.plan_name}` : ""}`));
        const tdS = createElement("td");
        tdS.appendChild(statusBadge(c.status));
        tr.appendChild(tdS);
        tr.appendChild(createElement("td", "", c.assigned_business_name ? `${c.assigned_business_name} (${c.assigned_user_email})` : "Unassigned"));
        tr.appendChild(createElement("td", "", `${c.use_count}/${c.max_uses} uses • ${fmtDate(c.created_at)}`));

        const tdA = createElement("td");
        const cluster = createElement("div", "admin-action-cluster");
        if (c.status === "AVAILABLE" || c.status === "ASSIGNED") {
          if (!c.assigned_user_id) {
            const assignBtn = createElement("button", "btn btn-sm", "Assign User");
            assignBtn.type = "button";
            assignBtn.addEventListener("click", () => {
              openModal({
                title: `Assign Code ${c.code_value}`,
                small: true,
                renderBody: (b, close) => {
                  const selWrap = createElement("div", "form-field");
                  selWrap.appendChild(createElement("label", "form-label", "Select Business Account"));
                  const sel = createElement("select", "form-input");
                  for (const u of usersRes.items) {
                    const opt = createElement("option", "", `${u.business_name} (${u.email})`);
                    opt.value = String(u.id);
                    sel.appendChild(opt);
                  }
                  selWrap.appendChild(sel);
                  const actions = createElement("div", "form-actions");
                  const cb = createElement("button", "btn", "Cancel");
                  cb.type = "button";
                  cb.addEventListener("click", close);
                  const sb = createElement("button", "btn btn-primary", "Assign Code");
                  sb.type = "button";
                  sb.addEventListener("click", async () => {
                    try {
                      await assignAdminCode(c.id, Number(sel.value));
                      showToast(`Assigned ${c.code_value}.`, "success");
                      close();
                      await renderCodes(container);
                    } catch (err) {
                      handleError(err, "Assign failed.");
                    }
                  });
                  actions.append(cb, sb);
                  b.append(selWrap, actions);
                },
              });
            });
            cluster.appendChild(assignBtn);
          } else {
            const redBtn = createElement("button", "btn btn-sm btn-primary", "Activate Now");
            redBtn.type = "button";
            redBtn.addEventListener("click", async () => {
              try {
                await redeemAdminCodeForUser(c.id, c.assigned_user_id, true);
                showToast(`Code ${c.code_value} activated.`, "success");
                await renderCodes(container);
              } catch (err) {
                handleError(err, "Redemption failed.");
              }
            });
            cluster.appendChild(redBtn);
          }
          const revBtn = createElement("button", "btn btn-sm btn-danger", "Revoke");
          revBtn.type = "button";
          revBtn.addEventListener("click", async () => {
            await revokeAdminCode(c.id, "Revoked by admin");
            showToast("Code revoked.", "info");
            await renderCodes(container);
          });
          cluster.appendChild(revBtn);
        }
        tdA.appendChild(cluster);
        tr.appendChild(tdA);
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      scroll.appendChild(table);
      listCard.appendChild(scroll);
      container.appendChild(listCard);
      container.appendChild(
        renderPaginationBar({
          page: codesRes.page,
          totalPages: codesRes.total_pages,
          total: codesRes.total,
          onPageChange: (nextPage) => {
            cache.codeFilters.page = nextPage;
            void renderCodes(container);
          },
        })
      );
    } catch (err) {
      handleError(err, "Failed to load activation codes.");
    }
  }

  async function renderPlans(container) {
    container.replaceChildren();
    try {
      const plans = await fetchAdminPlans(true);
      cache.plans = plans;
      container.replaceChildren();

      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", "Subscription Plans & Feature Limits"));
      hw.appendChild(createElement("p", "section-subtitle", "Configure plan durations, pricing, resource quotas, and feature flags."));
      hdr.appendChild(hw);
      const newPlanBtn = createElement("button", "btn btn-primary", "+ Create Plan");
      newPlanBtn.type = "button";
      newPlanBtn.addEventListener("click", () => openPlanModal(null, () => renderPlans(container)));
      hdr.appendChild(newPlanBtn);
      container.appendChild(hdr);

      const grid = createElement("div", "admin-charts-grid");
      for (const p of plans) {
        const card = createElement("section", "card");
        const ch = createElement("div", "card-header");
        ch.appendChild(createElement("h3", "card-title", `${p.name} (${p.code})`));
        ch.appendChild(statusBadge(p.status));
        card.appendChild(ch);
        card.appendChild(createElement("p", "metric-value", `${p.currency_code} ${p.price} / ${p.duration_days} days`));
        card.appendChild(createElement("p", "section-subtitle", p.description || "Configurable commercial SaaS tier."));
        card.appendChild(
          createElement(
            "p",
            "history-item-meta",
            `Limits: Invoices ${p.max_invoices ?? "∞"} • Customers ${p.max_customers ?? "∞"} • Products ${p.max_products ?? "∞"} • Themes: ${p.allow_custom_themes ? "Yes" : "No"}`
          )
        );
        const editBtn = createElement("button", "btn btn-sm", "Edit Plan");
        editBtn.type = "button";
        editBtn.addEventListener("click", () => openPlanModal(p, () => renderPlans(container)));
        card.appendChild(editBtn);
        grid.appendChild(card);
      }
      container.appendChild(grid);
    } catch (err) {
      handleError(err, "Failed to load plans.");
    }
  }

  function openPlanModal(existing, onDone) {
    openModal({
      title: existing ? `Edit Plan — ${existing.name}` : "Create Subscription Plan",
      renderBody: (body, close) => {
        const form = createElement("form", "form-stack");
        const errBox = createElement("div", "alert alert-error is-hidden");
        const codeF = createField({ id: "pl-code", name: "code", label: "Plan Code *", value: existing?.code || "", required: true, placeholder: "annual_pro" });
        const nameF = createField({ id: "pl-name", name: "name", label: "Plan Name *", value: existing?.name || "", required: true, placeholder: "Annual Pro" });
        const durF = createField({ id: "pl-dur", name: "duration_days", label: "Duration Days *", type: "number", value: String(existing?.duration_days ?? 30), required: true });
        const priceF = createField({ id: "pl-price", name: "price", label: "Price *", type: "number", step: "0.01", value: String(existing?.price ?? "0.00"), required: true });
        const maxInv = createField({ id: "pl-minv", name: "max_invoices", label: "Max Invoices (Blank = Unlimited)", type: "number", value: existing?.max_invoices ?? "" });
        const maxCust = createField({ id: "pl-mcust", name: "max_customers", label: "Max Customers (Blank = Unlimited)", type: "number", value: existing?.max_customers ?? "" });
        const maxProd = createField({ id: "pl-mprod", name: "max_products", label: "Max Products (Blank = Unlimited)", type: "number", value: existing?.max_products ?? "" });
        const themesChk = createCheckboxField({ id: "pl-themes", name: "allow_custom_themes", label: "Allow Custom Invoice Themes", checked: existing ? existing.allow_custom_themes : true });
        const reportsChk = createCheckboxField({ id: "pl-rep", name: "allow_reports", label: "Allow Sales Reports & Export", checked: existing ? existing.allow_reports : true });

        const actions = createElement("div", "form-actions");
        const cancel = createElement("button", "btn", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", close);
        const save = createElement("button", "btn btn-primary", existing ? "Save Plan" : "Create Plan");
        save.type = "submit";
        actions.append(cancel, save);

        form.append(errBox, codeF.wrapper, nameF.wrapper, durF.wrapper, priceF.wrapper, maxInv.wrapper, maxCust.wrapper, maxProd.wrapper, themesChk.wrapper, reportsChk.wrapper, actions);
        form.addEventListener("submit", async (e) => {
          e.preventDefault();
          save.disabled = true;
          const payload = {
            code: codeF.input.value.trim(),
            name: nameF.input.value.trim(),
            duration_days: Number(durF.input.value),
            price: Number(priceF.input.value),
            currency_code: existing?.currency_code || "INR",
            status: existing?.status || "ACTIVE",
            max_invoices: maxInv.input.value ? Number(maxInv.input.value) : null,
            max_customers: maxCust.input.value ? Number(maxCust.input.value) : null,
            max_products: maxProd.input.value ? Number(maxProd.input.value) : null,
            allow_custom_themes: themesChk.input.checked,
            allow_reports: reportsChk.input.checked,
            allow_pdf_export: true,
          };
          try {
            if (existing) {
              await updateAdminPlan(existing.id, payload);
            } else {
              await createAdminPlan(payload);
            }
            showToast("Subscription plan saved.", "success");
            close();
            await onDone();
          } catch (err) {
            save.disabled = false;
            errBox.textContent = err instanceof Error ? err.message : "Failed to save plan.";
            errBox.classList.remove("is-hidden");
          }
        });
        body.appendChild(form);
      },
    });
  }

  async function renderNotifications(container) {
    container.replaceChildren();
    try {
      const data = await fetchAdminNotifications();
      container.replaceChildren();
      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", "Admin Notifications"));
      hw.appendChild(createElement("p", "section-subtitle", `${data.unread_count} unread alert(s) across registrations, resets, and expirations.`));
      hdr.appendChild(hw);
      const readAllBtn = createElement("button", "btn btn-primary", "Mark All Read");
      readAllBtn.type = "button";
      readAllBtn.addEventListener("click", async () => {
        await markAllAdminNotificationsRead();
        await renderNotifications(container);
      });
      hdr.appendChild(readAllBtn);
      container.appendChild(hdr);

      const card = createElement("section", "card");
      if (data.items.length === 0) {
        card.appendChild(createElement("p", "section-subtitle", "No admin notifications recorded."));
      } else {
        const list = createElement("div", "history-list");
        for (const n of data.items) {
          const item = createElement("div", "history-item");
          const head = createElement("div", "history-item-head");
          head.appendChild(createElement("strong", "", n.title));
          head.appendChild(statusBadge(n.is_read ? "READ" : n.severity));
          item.append(head, createElement("p", "history-item-meta", `${n.message} • ${fmtDateTime(n.created_at)}`));
          if (!n.is_read) {
            const rb = createElement("button", "btn btn-sm", "Mark Read");
            rb.type = "button";
            rb.addEventListener("click", async () => {
              await markAdminNotificationRead(n.id);
              await renderNotifications(container);
            });
            item.appendChild(rb);
          }
          list.appendChild(item);
        }
        card.appendChild(list);
      }
      container.appendChild(card);
    } catch (err) {
      handleError(err, "Failed to load notifications.");
    }
  }

  async function renderAuditLogs(container) {
    container.replaceChildren();
    try {
      const data = await fetchAdminAuditLogs({ ...cache.auditFilters, page_size: 40 });
      container.replaceChildren();
      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", "Administrator Audit Logs"));
      hw.appendChild(createElement("p", "section-subtitle", `${data.total} immutable governance actions logged.`));
      hdr.appendChild(hw);
      container.appendChild(hdr);

      const card = createElement("section", "card");
      const scroll = createElement("div", "table-scroll");
      const table = createElement("table", "data-table");
      const thead = createElement("thead");
      const hr = createElement("tr");
      for (const h of ["Timestamp", "Actor", "Action", "Target", "Details"]) {
        hr.appendChild(createElement("th", "", h));
      }
      thead.appendChild(hr);
      table.appendChild(thead);

      const tbody = createElement("tbody");
      for (const l of data.items) {
        const tr = createElement("tr");
        tr.appendChild(createElement("td", "", fmtDateTime(l.created_at)));
        tr.appendChild(createElement("td", "", l.actor_email || "System"));
        tr.appendChild(createElement("td", "", l.action));
        tr.appendChild(createElement("td", "", `${l.target_type}${l.target_id ? ` #${l.target_id}` : ""}`));
        tr.appendChild(createElement("td", "cell-secondary", l.details_json ? JSON.stringify(l.details_json) : "—"));
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      scroll.appendChild(table);
      card.appendChild(scroll);
      container.appendChild(card);
      container.appendChild(
        renderPaginationBar({
          page: data.page,
          totalPages: data.total_pages,
          total: data.total,
          onPageChange: (nextPage) => {
            cache.auditFilters.page = nextPage;
            void renderAuditLogs(container);
          },
        })
      );
    } catch (err) {
      handleError(err, "Failed to load audit logs.");
    }
  }

  async function renderSettings(container) {
    container.replaceChildren();
    try {
      const cfg = await fetchAdminSettings();
      container.replaceChildren();

      const hdr = createElement("div", "section-header");
      const hw = createElement("div");
      hw.appendChild(createElement("h2", "section-heading", "Global SaaS & Admin Settings"));
      hw.appendChild(createElement("p", "section-subtitle", "Control enforcement policies, notification schedule, support contact details, and your admin password."));
      hdr.appendChild(hw);
      container.appendChild(hdr);

      const grid = createElement("div", "admin-charts-grid");

      // Global SaaS policy form
      const cfgCard = createElement("section", "card");
      cfgCard.appendChild(createElement("h3", "card-title", "Platform Governance Settings"));
      const form = createElement("form", "form-stack");
      const enf = createCheckboxField({
        id: "st-enforce",
        name: "enforce_subscription_expiry",
        label: "Enforce subscription expiry on write APIs",
        checked: cfg.enforce_subscription_expiry,
      });
      const selfAct = createCheckboxField({
        id: "st-self",
        name: "allow_self_activation",
        label: "Allow approved users to self-redeem activation codes",
        checked: cfg.allow_self_activation,
      });
      const intF = createField({
        id: "st-int",
        name: "notification_intervals_days",
        label: "Expiry Notification Intervals (days)",
        value: cfg.notification_intervals_days,
        required: true,
      });
      const supEmail = createField({
        id: "st-sup-e",
        name: "support_email",
        label: "Support Contact Email *",
        type: "email",
        value: cfg.support_email,
        required: true,
      });
      const supPhone = createField({
        id: "st-sup-p",
        name: "support_phone",
        label: "Support Contact Phone *",
        value: cfg.support_phone,
        required: true,
      });
      const saveBtn = createElement("button", "btn btn-primary", "Save Platform Settings");
      saveBtn.type = "submit";
      form.append(enf.wrapper, selfAct.wrapper, intF.wrapper, supEmail.wrapper, supPhone.wrapper, saveBtn);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await saveAdminSettings({
            enforce_subscription_expiry: enf.input.checked,
            allow_self_activation: selfAct.input.checked,
            notification_intervals_days: intF.input.value.trim(),
            support_email: supEmail.input.value.trim(),
            support_phone: supPhone.input.value.trim(),
          });
          showToast("Platform settings updated.", "success");
        } catch (err) {
          handleError(err, "Failed to update settings.");
        }
      });
      cfgCard.appendChild(form);
      grid.appendChild(cfgCard);

      // Admin password update card
      const pwdCard = createElement("section", "card");
      pwdCard.appendChild(createElement("h3", "card-title", "Change Administrator Password"));
      const pwdForm = createElement("form", "form-stack");
      const curF = createField({ id: "adp-cur", name: "current_password", label: "Current Password *", type: "password", required: true });
      const newF = createField({ id: "adp-new", name: "new_password", label: "New Password *", type: "password", required: true, help: "Minimum 10 characters." });
      const conF = createField({ id: "adp-con", name: "confirm_password", label: "Confirm New Password *", type: "password", required: true });
      const chgBtn = createElement("button", "btn btn-primary", "Update Admin Password");
      chgBtn.type = "submit";
      pwdForm.append(curF.wrapper, newF.wrapper, conF.wrapper, chgBtn);
      pwdForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          const res = await changeAdminPassword({
            current_password: curF.input.value,
            new_password: newF.input.value,
            confirm_password: conF.input.value,
          });
          onAdminUpdated(res.admin);
          pwdForm.reset();
          showToast("Administrator password updated.", "success");
        } catch (err) {
          handleError(err, "Password update failed.");
        }
      });
      pwdCard.appendChild(pwdForm);
      grid.appendChild(pwdCard);

      container.appendChild(grid);
    } catch (err) {
      handleError(err, "Failed to load admin settings.");
    }
  }

  return {
    mount(section, container) {
      if (section === "overview") return renderOverview(container, false);
      if (section === "reports") return renderOverview(container, true);
      if (section === "approvals") return renderUsers(container, true);
      if (section === "users") return renderUsers(container, false);
      if (section === "subscriptions") return renderSubscriptions(container);
      if (section === "codes") return renderCodes(container);
      if (section === "plans") return renderPlans(container);
      if (section === "notifications") return renderNotifications(container);
      if (section === "audit") return renderAuditLogs(container);
      if (section === "settings") return renderSettings(container);
      return renderOverview(container, false);
    },
  };
}
