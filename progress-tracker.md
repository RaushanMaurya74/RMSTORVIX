# Progress Tracker — Invoice & Billing System

## Current Phase
- Complete Sidebar Navigation & SPA Routing, Safe Permanent Invoice Deletion, Global Dark/Bright Theme System, and Responsive Fixes implemented and verified end-to-end.

## Current Goal
- System is ready for use at `http://127.0.0.1:8000/`.

## Completed
- **Phases 1–5**: Core Invoice & Billing System (FastAPI, PostgreSQL `19.0`, Alembic `0001`–`0004`, auth sessions, Business Settings, Customers, Products/Services, Invoices + `fpdf2` PDFs, Payments, Reports + CSV export + Audit Trail).
- **Post-Completion Enhancements (`0005_hsn_gst_history_bank`)**:
  - **Feature 1 — Invoice Edit, GST Split (CGST / SGST / IGST), Cancellation & Modification History**:
    - Added `gst_mode` (`auto`, `cgst_sgst`, `igst`), `gst_type`, `cgst_amount`, `sgst_amount`, `igst_amount`, `cancelled_at`, `cancellation_reason`, item-level GST rates/amounts, and `invoice_modifications` table (`backend/app/models/invoice.py`, `invoice_service.py`, `api/invoices.py`).
    - Authorized users can edit both `draft` and unpaid `issued` invoices (`amount_paid == 0.00`), recalculating subtotal, discount, CGST, SGST, IGST, total tax, grand total, and balance due on the server, auto-refreshing stored PDFs, and recording who modified what and when (`invoice_modifications` + `audit_events`).
    - Protected `partially_paid`, `paid`, and cancelled (`void`) invoices from unsafe editing (`409 Conflict`). Draft deletion and unpaid invoice cancellation (with optional reason) preserve audit history.
    - Updated `invoicesView.js` with GST mode selector, line-item HSN/GST editing, cancellation reason dialog, and Modification History timeline.
  - **Feature 2 — HSN Code, Purchase/Selling Price & Stock Quantity in Product Management**:
    - Added `hsn_code` (optional 4/6/8-digit validated), `purchase_price`, `selling_price` alias (`unit_price`), and `stock_quantity` to `Product` (`models/product.py`, `schemas/product.py`, `services/product_service.py`).
    - Propagated HSN code onto invoice items, printable invoice sheet, `fpdf2` PDFs (`pdf_service.py`), and `HSN Summary` report (`report_service.py`, `reportsView.js`).
    - Updated `productsView.js` to display Product ID, Name/SKU, HSN Code, Purchase Price, Selling Price, GST Rate, Stock Quantity, and Status.
  - **Feature 3 — Business Bank Details & Amount-Specific Payment QR Code**:
    - Added `bank_account_holder`, `bank_name`, `bank_account_number`, `bank_ifsc_code`, `bank_branch`, and `upi_id` to `Business` (`models/business.py`, `schemas/business.py`, Business Settings form in `ui.js`).
    - Added `qrcode`-based amount-specific UPI payment QR generation (`services/qr_service.py`, `GET /api/v1/invoices/{id}/qr`), embedded bank details & QR code on both the printable Invoice Detail sheet and `fpdf2` invoice PDFs (omitted when `draft`, `void`, or `balance_due == 0`).
  - **Verification**:
    - `node --check` passed on all 10 frontend JS modules (`JS_CHECK_PASSED`).
    - `pytest` in `backend/` passed (`29 passed`, zero warnings in project code).
    - `alembic upgrade head` applied `0005_hsn_gst_history_bank` onto PostgreSQL `19.0`.
    - Live `uvicorn` + PostgreSQL smoke check (`LIVE_ENHANCEMENTS_SMOKE_PASSED`) verified bank/UPI config, HSN product creation, intra-state CGST+SGST & inter-state IGST, QR PNG (`\x89PNG`), PDF generation (`%PDF-`), editing unpaid issued invoices with modification history & PDF refresh, HSN summary report, and invoice cancellation with reason.
- **Visual Signature & GSTIN Verification (`0006_signature_and_gstin`)**:
  - **Visual Signature on Invoices**:
    - Added `signature_storage_key`, `signature_mime_type`, `signature_enabled`, `signature_placement` (`bottom_left`, `bottom_center`, `bottom_right`), and `signature_updated_at` on `Business` (`models/business.py`, `schemas/business.py`, `services/signature_service.py`, `api/business.py`).
    - Added Pillow MIME/image validation (PNG, JPEG, WebP), byte/dimension limits (`SIGNATURE_MAX_BYTES`), path containment in `STORAGE_SIGNATURE_DIR` (`storage/signatures`), and authenticated endpoints (`GET`/`POST`/`DELETE /api/v1/business/signature`) plus `BusinessProfileResponse.has_signature` (no filesystem paths exposed).
    - Added Business Settings signature upload/preview/replace/remove controls, enable toggle, and placement selector (`frontend/js/ui.js`), plus Authorized Signatory rendering in invoice preview (`invoicesView.js`) and aspect-ratio-preserving `fpdf2` PDF generation (`pdf_service.py`).
  - **GSTIN Verification & Auto-Fill**:
    - Added `gstin_verified` on `Customer` (`models/customer.py`, `schemas/customer.py`), built-in 15-character Indian GSTIN format + mod-36 check-digit verification + State/Country/PAN extraction, and optional external lookup adapter (`GSTIN_API_URL`, `GSTIN_API_KEY`, `GSTIN_API_TIMEOUT_SECONDS`) in `services/gstin_service.py` and `POST /api/v1/customers/verify-gstin` (`api/customers.py`).
    - Added `Verify GSTIN` action and verified status badge in the Customer modal and list (`frontend/js/customersView.js`).
  - **Verification**:
    - `node --check` passed on all 10 frontend JS modules (`JS_CHECK_PASSED`).
    - `pytest` in `backend/` passed (`31 passed`, 1 third-party `StarletteDeprecationWarning`).
    - `alembic upgrade head` applied `0006_signature_and_gstin` onto PostgreSQL `19.0`.
    - Live `uvicorn` + PostgreSQL smoke check (`LIVE_SMOKE_SIG_GSTIN_PASSED`) verified auth guards (`401`), PNG/WebP upload & replacement, placement updates, invalid/valid GSTIN verification + customer creation, invoice preview `signature` metadata, PDF generation (`%PDF-`), and signature deletion (`404` on subsequent fetch).
- **Sidebar Slider Fix, Business Logo & Custom Invoice Themes (`0007_logo_and_invoice_theme`)**:
  - **Sidebar Slider Fix**:
    - Fixed `#menu-toggle-btn` visibility at all viewport sizes, added persistent desktop collapsible sidebar (`.app-shell.sidebar-collapsed` via `localStorage`), fixed single-bind event registration in `frontend/js/app.js`, fixed mobile `100dvh` slide drawer + backdrop overlay (`Escape` and outside-click close), and eliminated mobile topbar overlap under `<= 640px`.
  - **Business Logo Management**:
    - Added `logo_storage_key`, `logo_mime_type`, `logo_updated_at` on `Business` and `STORAGE_LOGO_DIR` / `LOGO_MAX_BYTES` configuration, extracting shared image validation/containment into `backend/app/services/media_service.py` with thin logo & signature wrappers (`logo_service.py`, `signature_service.py`).
    - Added authenticated endpoints `GET`/`POST`/`PUT`/`DELETE /api/v1/business/logo`, client-side pre-upload preview via `URL.createObjectURL`, dashboard/sidebar header logo rendering with graceful fallback, invoice preview logo, and aspect-ratio-preserving `fpdf2` PDF logo rendering.
  - **Custom Invoice Themes & Live Preview**:
    - Added `invoice_theme_preset` and 7 hex color columns (`theme_primary_color`, `theme_secondary_color`, `theme_accent_color`, `theme_header_color`, `theme_table_header_color`, `theme_text_color`, `theme_border_color`), server-side `#RRGGBB` validation (`schemas/common.py`), 8 presets (`classic_blue`, `elegant_black`, `emerald_green`, `royal_purple`, `modern_orange`, `minimal_grey`, `crimson_red`, `teal_professional`) in `theme_service.py`, and `GET /api/v1/business/appearance`, `GET`/`PUT /api/v1/business/theme`.
    - Added Business Settings sections (`Business Profile`, `Business Logo`, `Authorized Visual Signature`, `Invoice Appearance / Invoice Theme`, `Invoice Theme Presets`, `Custom Colors`, `Live Preview`) via `frontend/js/themePreview.js` and `ui.js`, plus themed live/print invoice sheets (`invoicesView.js`) and themed `fpdf2` PDFs with luminance-contrast text selection (`pdf_service.py`).
  - **Verification**:
    - `node --check` passed on all 11 frontend JS modules (`JS_CHECK_PASSED`).
    - `pytest` in `backend/` passed (`33 passed, 1 warning in 32.81s`).
    - `alembic upgrade head` applied `0007_logo_and_invoice_theme` onto PostgreSQL `19.0`.
    - Live `uvicorn` + PostgreSQL smoke check (`LIVE_SMOKE_LOGO_THEME_PASSED`) and live browser QA (`1280x800` desktop + `390x844` mobile) verified sidebar expand/collapse, mobile toggle/Escape/backdrop close with zero element occlusion, presets/custom color live preview + reset, and `0` console errors.
- **Complete Sidebar Navigation, Safe Permanent Invoice Deletion & Global Dark/Bright Mode**:
  - **Sidebar Navigation & SPA Refresh Persistence**:
    - Added semantic `<a href="#/...">` navigation across all 9 sidebar modules (`Dashboard`, `Invoices`, `Customers`, `Products / Services`, `Inventory / Stock`, `Payments`, `Reports`, `Notifications`, `Business Settings`) plus `inventoryView.js` (stock tracking & adjust stock modal backed by `/api/v1/products`) and `notificationsView.js` (overdue invoice alerts, low-stock warnings, audit activity backed by `/api/v1/invoices`, `/products`, `/reports/audit`).
    - Added `#/...` URL hash + `hashchange` routing in `app.js`, FastAPI SPA HTML fallbacks (`/dashboard`, `/invoices`, `/invoices/new`, `/invoices/{invoice_id}`, `/customers`, `/products`, `/inventory`, `/payments`, `/reports`, `/notifications`, `/settings`) and `Cache-Control: no-store, max-age=0` on HTML/CSS/JS in `main.py`, plus viewport resize fallback syncing (`innerWidth <= 768`).
  - **Safe Permanent Invoice Deletion**:
    - Extended `DELETE /api/v1/invoices/{invoice_id}` (`invoice_service.py`, `schemas/invoice.py`, `api/invoices.py`) with row-level `FOR UPDATE` locking, recorded-payment safeguard (`Payment` count + `amount_paid` check), permanent DB + PDF cleanup for eligible `draft` and unpaid `void` invoices, SQLAlchemy transaction rollback guard, and sanitized `invoice.deleted` audit logging (`is_deletable` & `delete_block_reason`).
    - Added `Delete`, `Cancel`, and locked-delete controls in the Invoice List table action column and `Delete Permanently` in Invoice Detail (`invoicesView.js`), with confirmation dialogs showing invoice numbers/amounts and global toast notifications (`showToast` in `dom.js`).
  - **Global Dark Mode & Bright Mode**:
    - Implemented centralized `:root[data-theme="light"]` and `:root[data-theme="dark"]` design tokens (`--bg-primary`, `--bg-secondary`, `--surface`, `--surface-hover`, `--text-primary`, `--text-secondary`, `--border-color`, `--primary-color`, `--input-background`, `--sidebar-background`, `--modal-background`, `--overlay-backdrop`) in `tokens.css` & `styles.css`, anti-FOUC `<head>` script in `index.html`, `#theme-mode-toggle` in the topbar and auth screen (`ui.js`), `localStorage` persistence (`inv_color_theme`), and asset cache-busting (`?v=20261126`).
  - **Verification**:
    - `node --check` passed on all 13 frontend JS modules (`JS_CHECK_PASSED`).
    - `pytest` in `backend/` passed (`35 passed, 1 warning in 32.44s`), including new permanent delete/cascade/safeguard and SPA route tests.
    - Live `uvicorn` + PostgreSQL smoke test (`LIVE_SMOKE_PERM_DELETE_PASSED`) verified all SPA routes, auth `401`/cross-business `404` guards, `409` guards on active issued & paid invoices, permanent DB row + item + modification + PDF removal on eligible draft and void invoices, and clean cleanup.
    - Live browser QA (`http://127.0.0.1:8000`) verified 0 console errors, all 9 sidebar routes, page refresh on `#/customers` and direct `/invoices`, Dark Mode persistence across reloads and solid dark modals/inputs/cards/sidebar/tables, and responsive `1280x800`, `1024x768`, `768x1024`, and `390x844` drawer open/Escape/backdrop close.

- **Completed Phase — Major SaaS Upgrade: Multi-Tenant Approval Workflow, Subscriptions, Activation Codes & Admin Panel (`/admin`)**:
  - **Liquid Glass SaaS Auth & Account Gate (`frontend/js/authView.js`, `frontend/css/styles.css`)**:
    - Redesigned Login & Registration pages with floating GST/Collection/HSN billing showcase cards, frosted glassmorphism cards, Dark/Bright theme switch, show/hide password toggles, Remember Me (30 days), Forgot Password modal alerting admin, full registration fields (Owner Name, Business Name, Mobile, Email, GSTIN, Business Type, Address, Confirm Password, Terms), and Pending Approval / Not-Activated gate screen with administrator support details.
  - **Approval Workflow, Subscriptions & Activation Code Engine (`backend/alembic/versions/0008_saas_admin_subscriptions.py`, `backend/app/models/saas.py`, `backend/app/services/saas_service.py`, `backend/app/api/subscription.py`)**:
    - Implemented separated `approval_status` & `subscription_status` lifecycle; self-registrations enter `PENDING_APPROVAL` + `NOT_ACTIVATED` and cannot bypass approval with an activation code (`403`).
    - Added cryptographic `RMX-XXXX-XXXX-XXXX` codes (`secrets`), single/batch generation, `FOR UPDATE` redemption locking, assignment/revocation/expiry checks, attempt rate limiting (`429`), CSV export, configurable notification thresholds (`30,15,7,3,1,0` days), plan feature/quota limits (`max_invoices`, `max_customers`, `max_products`, `max_users`, `allow_reports`, `allow_pdf_export`, `allow_custom_themes`), and expiry write-lock vs read/CSV-export accessibility.
    - Non-destructively backfilled existing pre-SaaS accounts in Alembic `0008` so `RR ENTERPRISES` remains `ACTIVE` cleanly.
  - **Isolated Dark Liquid-Glass Admin Control Plane (`/admin`, `frontend/admin.html`, `frontend/css/admin.css`, `frontend/js/admin*.js`, `backend/app/api/admin.py`, `backend/app/services/admin_service.py`, `backend/scripts/seed_admin.py`)**:
    - Separate `admin_users` & `admin_sessions` (`rmx_admin_session` cookie), initial admin seeded strictly from `.env` (`ensure_initial_admin`) with mandatory password rotation on first login (`must_change_password`), and all 10 admin modules (`Admin Dashboard` KPIs & charts, `Pending Approvals`, `User Management`, `Subscriptions`, `Activation Codes`, `Plans & Quotas`, `Notifications`, `SaaS Reports`, `Audit Logs`, `Admin Settings`).
  - **Main Workspace Subscription Controls (`frontend/js/subscriptionView.js`, `frontend/js/notificationsView.js`, `frontend/js/ui.js`, `frontend/js/app.js`, `frontend/index.html`)**:
    - Added live server-synced subscription countdown card on Dashboard & `Subscription` page, `Activation` page for `RMX-` code redemption, expiry warning banners, and real SaaS & expiry alerts inside `Notifications`.
  - **Verification**:
    - `node --check` passed on all frontend JS modules (`ALL_JS_OK`).
    - `pytest backend/tests -q` passed (`39 passed, 1 warning in 216.03s`, including `test_saas_admin.py`).
    - Live PostgreSQL 19.0 Alembic migration `0008_saas_admin_subscriptions` + `seed_admin.py` + `smoke_saas.py` passed (`0` errors, temporary smoke rows cleaned).
    - Live browser QA across `http://127.0.0.1:8000/` and `http://127.0.0.1:8000/admin` on desktop (`1366x800`) and mobile (`390x844`) verified zero console errors and zero layout overflow.

## In Progress
- None.

## Next Up
- Ready for production hardening or any additional feature requests.

## Open Questions
- Stock auto-deduction: `stock_quantity` is currently managed manually/informational so Services and zero-stock catalog items are never blocked during invoicing; automatic stock deduction/restoration can be added if inventory enforcement is desired.

## Architecture Decisions
- Backend: FastAPI (`create_app()` factory in `backend/app/main.py`, versioned API prefix `/api/v1` plus root `/health`).
- Database: PostgreSQL via SQLAlchemy 2.x, `psycopg`, and Alembic migrations (`0001` through `0008`).
- PDF & QR Generation: `fpdf2` + `qrcode` (Pillow) generating authorized business-scoped invoice PDFs and amount-specific UPI QR PNGs.
- Frontend: Modular HTML/CSS/JavaScript served from `frontend/` using CSS custom properties from `ui-context.md` and safe `textContent` DOM rendering.

## Session Notes
- 2026-11-26: Complete Sidebar Navigation & SPA Routing, Safe Permanent Invoice Deletion, and Global Dark/Bright Mode implemented and verified (`35 passed` in `pytest`, `JS_CHECK_PASSED` on 13 JS modules, `LIVE_SMOKE_PERM_DELETE_PASSED`, desktop/laptop/tablet/mobile browser QA verified with `0` console errors). Live server running at `http://127.0.0.1:8000`.
- Update this tracker after each completed implementation unit.
- Do not mark features completed until verified.
