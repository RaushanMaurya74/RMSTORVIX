# Architecture Context — Invoice & Billing System

## Stack
- Frontend: HTML, CSS, JavaScript (modular SPA with `#/...` hash + server-side SPA route fallbacks, responsive collapsible sidebar/drawer, and anti-FOUC Light/Dark CSS custom property theme tokens persisted in `localStorage`)
- Backend: Python, FastAPI
- Database: PostgreSQL
- ORM and migrations: SQLAlchemy 2.x and Alembic
- API validation: Pydantic
- PDF, Logos, Signatures & Themes: `fpdf2` server-side PDF generation stored in `STORAGE_PDF_DIR` (`storage/pdfs`) scoped per business (`biz_<id>/invoice_<id>_<number>.pdf`) and served only through authenticated ownership checks. Amount-specific UPI payment QR codes (`qrcode`) are generated on the server for unpaid issued invoices when a business UPI ID is configured. Uploaded visual signature images (`STORAGE_SIGNATURE_DIR`) and business logos (`STORAGE_LOGO_DIR`) support PNG, JPEG, and WebP scoped per business (`biz_<id>/signature.<ext>`, `biz_<id>/logo.<ext>`) and are served only through authenticated business-scoped endpoints (`GET /api/v1/business/signature`, `GET /api/v1/business/logo`) without exposing filesystem paths. Custom invoice themes (`classic_blue`, `elegant_black`, `emerald_green`, `royal_purple`, `modern_orange`, `minimal_grey`, `crimson_red`, `teal_professional`, or custom hex palettes) apply consistently to live invoice previews, print views, and `fpdf2` PDFs.
- Authentication: server-side database-backed sessions (`user_sessions`) using opaque random tokens (`secrets.token_urlsafe(32)`), storing only SHA-256 token hashes in PostgreSQL and delivering the token via an `HttpOnly`, `SameSite=Lax` cookie (`inv_session`, `Secure` configurable via `COOKIE_SECURE`). Passwords are hashed with salted `scrypt` (`hashlib.scrypt` with per-user random salt and `hmac.compare_digest` verification). Each registered user is initially linked to a dedicated `Business` record (`users.business_id`) so all business, customer, product, invoice, payment, and audit queries remain strictly scoped by `business_id`.
- SaaS Governance & Separate Admin Panel (`/admin`): isolated `admin_users` & `admin_sessions` (`rmx_admin_session` cookie) seeded via `.env` (`INITIAL_ADMIN_*` / `backend/scripts/seed_admin.py`) with mandatory first-login password rotation (`must_change_password`). Separates user `approval_status` (`PENDING_APPROVAL`, `APPROVED`, `ACTIVE`, `INACTIVE`, `SUSPENDED`, `REJECTED`) from `subscription_status` (`NOT_ACTIVATED`, `ACTIVE`, `EXPIRED`, `SUSPENDED`, `CANCELLED`). Registration creates `PENDING_APPROVAL` + `NOT_ACTIVATED` accounts blocked from billing routes until administrator approval and subscription activation (via manual plan assignment or `RMX-XXXX-XXXX-XXXX` activation codes locked with `FOR UPDATE` + rate limiting). Expired subscriptions lock write mutations (`get_active_subscription_user`) while keeping read history, CSV export, notifications, support, and code renewal accessible.

## System Boundaries
- `frontend/`: user interface, client-side validation and API client.
- `backend/app/api/`: HTTP routes and request/response handling.
- `backend/app/services/`: business logic.
- `backend/app/models/`: database models.
- `backend/app/schemas/`: Pydantic schemas.
- `backend/app/core/`: settings, authentication, security and shared infrastructure.
- `backend/app/db/`: database connection and session management.
- `backend/tests/`: automated tests.
- `docs/`: technical and user documentation.

## Storage Model
- PostgreSQL stores user/business records, customer/product details, invoice metadata and line items, payment records, and audit events.
- Generated PDF files are stored in an application-managed file area; database records track metadata and ownership. Avoid storing generated binary content in ordinary database fields unless a documented requirement arises.
- Development secrets belong in environment variables and a local `.env` file excluded from version control.

## Auth and Access Model
- Protected endpoints require authenticated users.
- Users may only access records owned by their business/account unless a specific authorized role permits otherwise.
- Authorization is enforced server-side on every relevant operation.
- Passwords must be stored using a strong password hashing algorithm; never store plaintext passwords.

## Invariants
1. Invoice totals are calculated and validated on the server.
2. Invoice numbering must be unique within the configured business scope.
3. Invoice and related line-item creation/update must use database transactions.
4. Ownership and permissions are checked before reads, writes, PDF generation and downloads.
5. Audit events are append-oriented and must not expose secrets.
6. Do not expose private file paths or create unrestricted public download URLs.
