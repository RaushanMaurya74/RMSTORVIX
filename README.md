# RMSTORVIX IGNITE — Invoice, GST Billing & Multi-Tenant SaaS Platform

A full-stack, production-ready Invoice & Billing SaaS application built with **HTML/CSS/JavaScript**, **Python FastAPI**, **SQLAlchemy 2.x + Alembic**, **PostgreSQL (Supabase-ready)**, and **Vercel Python Serverless Functions**.

---

## Core Features

### Billing, Tax & Invoicing
- **Multi-Business Isolation**: Every business account owns isolated customers, products/services, inventory, invoices, payments, media assets, and audit logs.
- **Tax-Compliant GST Billing**: Automatic server-side `ROUND_HALF_UP` decimal calculations for item subtotals, discounts, HSN/SAC codes, CGST, SGST, IGST, and balance due.
- **Invoice Lifecycle & Safe Permanent Delete**: Draft editing, sequential transaction-locked numbering (`with_for_update`), issue/void flows, dynamic `overdue` state, invoice modification history, and accounting-safe permanent deletion for unpaid draft/void invoices.
- **Professional PDFs, Brand Assets & UPI QR**: Server-side `fpdf2` PDF generation supporting uploaded business logos, visual signatures with configurable placement, custom invoice color themes (`8+` presets + custom hex palettes), and amount-specific UPI payment QR codes.
- **Sales Reports & Audit Trail**: Date-filtered sales/tax/collections reports, formula-safe CSV invoice exports, and append-only operational audit logs.

### Multi-User SaaS Governance & Admin Control Plane (`/admin`)
- **Liquid Glass Authentication UI**: Responsive Login & Registration experience with Dark/Bright modes, Show/Hide password toggles, Remember Me sessions, and Forgot Password admin notifications.
- **Approval-Before-Activation Pipeline**: Newly registered business accounts enter `PENDING_APPROVAL` / `NOT_ACTIVATED` state and remain restricted from operational billing routes until reviewed and activated by an administrator.
- **Subscriptions & Cryptographic Activation Codes**: Single/batch `RMX-XXXX-XXXX-XXXX` code generation (`secrets`), row-locked redemption, expiry countdown timers, quota/feature limits per plan, configurable expiry alert thresholds, and read/export access on expired accounts.
- **Isolated Admin Console (`/admin`)**: Dedicated `admin_users` / `admin_sessions` (`rmx_admin_session`) portal with mandatory first-login password rotation and full governance dashboards, approvals, user/subscription management, code export, audit logs, and global policy settings.

---

## Technology Stack

- **Frontend**: Vanilla Modular HTML, CSS (Design Tokens, Light/Dark Mode, Liquid Glass UI), ES6 JavaScript (`frontend/`)
- **Backend**: Python 3.12+, FastAPI, Pydantic v2 (`backend/app/`, Vercel entrypoint `api/index.py`)
- **Database & Migrations**: PostgreSQL (Local / Supabase PostgreSQL), SQLAlchemy 2.x, `psycopg[binary]`, Alembic (`backend/alembic/`)
- **Persistent Object Storage**: Local disk (development) / Private Supabase Storage Bucket (Vercel production)
- **PDF & QR**: `fpdf2`, `Pillow`, `qrcode`

---

## Project Structure

```text
invoice-billing/
├── api/
│   └── index.py                  # Vercel Python ASGI entrypoint importing FastAPI app
├── backend/
│   ├── alembic/                  # Alembic migrations (0001..0008)
│   ├── alembic.ini
│   ├── app/
│   │   ├── api/                  # Versioned REST routes (/api/v1/*) & admin routes
│   │   ├── core/                 # Settings, DB dependencies, scrypt password/token security
│   │   ├── db/                   # SQLAlchemy engine & serverless pooler configuration
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic request/response schemas
│   │   ├── services/             # Business logic, storage adapter, PDF, SaaS & admin services
│   │   └── main.py               # FastAPI app factory, CORS, /app-config.js, SPA serving
│   ├── scripts/
│   │   └── seed_admin.py         # Idempotent initial administrator & SaaS defaults seeder
│   ├── tests/                    # Automated Pytest suite
│   ├── pyproject.toml
│   └── requirements.txt          # Backend + test dependencies
├── docs/
│   └── setup.md                  # Detailed local PostgreSQL & developer setup guide
├── frontend/
│   ├── admin.html                # Isolated Administrator Panel shell (/admin)
│   ├── index.html                # Main Business Workspace SPA shell (/)
│   ├── css/                      # Design tokens, app styles, and dark liquid-glass admin styles
│   └── js/                       # Modular API clients, views, countdown widgets & controllers
├── .env.example                  # Secret-free environment template
├── .gitignore                    # Excludes .env*, .venv, caches, local storage & artifacts
├── DEPLOYMENT.md                 # Step-by-step GitHub + Supabase + Vercel deployment guide
├── README.md                     # This file
├── requirements.txt              # Root production runtime dependencies for Vercel
└── vercel.json                   # Vercel Fluid Compute routing & Python function config
```

---

## Local Development Setup

### 1. Prerequisites
- Python 3.12+
- PostgreSQL 15+ (or a Supabase project database)
- Node.js 18+ (optional, for frontend `node --check` syntax verification)

### 2. Environment Configuration
Copy `.env.example` to `.env` and fill in your local PostgreSQL connection string and initial admin seed credentials:

```bash
cp .env.example .env
```

Key local settings:
- `APP_ENV=development`
- `DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/invoice_billing`
- `INITIAL_ADMIN_EMAIL=<your-admin-email>`
- `INITIAL_ADMIN_PASSWORD=<strong-initial-password>`
- `COOKIE_SECURE=false` (required only for local plain HTTP `127.0.0.1`; automatically enforced `true` in production/Vercel)

### 3. Install Dependencies & Apply Migrations

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r backend/requirements.txt

cd backend
alembic -c alembic.ini upgrade head
cd ..

python backend/scripts/seed_admin.py
```

### 4. Run Locally

```bash
uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8000 --reload
```

- Business Portal: `http://127.0.0.1:8000/`
- Admin Control Plane: `http://127.0.0.1:8000/admin`
- Health Endpoint: `http://127.0.0.1:8000/api/v1/health`

### 5. Run Tests

```bash
pytest backend/tests -q
```

---

## Production Deployment (GitHub + Vercel + Supabase)

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the full step-by-step production deployment manual covering GitHub setup, Supabase PostgreSQL Transaction Pooler (`:6543`), Alembic migrations, private Supabase Storage bucket configuration, Vercel environment variables, verification, and backups.

---

## Security Architecture

- **Credentials & Secret Hygiene**: Passwords use per-user salted `scrypt` hashing (`hashlib.scrypt`) and constant-time comparison (`hmac.compare_digest`). Session tokens and activation codes are hashed via SHA-256 before persistence (`user_sessions`, `admin_sessions`, `activation_codes`).
- **Browser Safety**: `HttpOnly`, `SameSite=Lax` cookies (`inv_session`, `rmx_admin_session`) with `Secure` enforced in production; `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, strict CORS origin whitelisting, and XSS-safe DOM rendering (`textContent`).
- **Private Media Access**: Business logos, visual signatures, and generated invoice PDFs live in business-scoped storage paths and are accessible only after server-side authentication and `business_id` verification.
- **No Secrets in Frontend or Git**: `.env` is excluded by `.gitignore`. Initial admin credentials, database URLs, and `SUPABASE_SERVICE_ROLE_KEY` never appear in browser JS or public API responses.
