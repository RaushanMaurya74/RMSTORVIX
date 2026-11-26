# Production Deployment Guide — GitHub + Vercel + Supabase

This guide covers deploying **RMSTORVIX IGNITE Invoice & Billing SaaS** using **GitHub** (source repository & CI trigger), **Vercel** (Python FastAPI + Fluid Compute hosting), and **Supabase** (PostgreSQL database + Private Storage bucket).

> [!IMPORTANT]
> Never commit `.env`, database passwords, `SUPABASE_SERVICE_ROLE_KEY`, or admin credentials to GitHub. Always verify `git status` before pushing.

---

## Architecture Overview

- **GitHub (`main` branch)**: Connected to Vercel for automatic builds and deployments on every push.
- **Vercel (`api/index.py` + `vercel.json`)**: Serves both the FastAPI REST API (`/api/v1/*`), `/app-config.js` runtime config, and modular HTML/CSS/JS frontend (`/`, `/admin`, `/css/*`, `/js/*`).
- **Supabase PostgreSQL**: Accessed via **Supavisor Transaction Pooler (port `6543`)** at runtime using `DATABASE_URL` with automatic `NullPool`, `sslmode=require`, and disabled prepared statements (`prepare_threshold=None`) for serverless safety. Migrations run separately against the **Session Pooler / Direct Connection (port `5432`)**.
- **Supabase Storage (`rmstorvix-private` bucket)**: Stores persistent business logos (`logos/biz_<id>/...`), digital signatures (`signatures/biz_<id>/...`), and cached invoice PDFs (`pdfs/biz_<id>/...`) privately behind backend authentication.

---

## Step 1 — Prepare & Push Repository to GitHub

1. Create a private repository on GitHub (e.g., `rmstorvix-invoice-billing`).
2. Confirm sensitive files are excluded (`.gitignore` already ignores `.env`, `.env.*`, `.venv/`, `storage/`, `backend/storage/`, `__pycache__/`):
   ```bash
   git init
   git add .
   git status
   ```
   Verify `.env` and `storage/` do **not** appear in `git status`.
3. Commit and push to GitHub:
   ```bash
   git commit -m "Prepare RMSTORVIX SaaS for Vercel and Supabase production"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```

---

## Step 2 — Create Supabase Project & Configure PostgreSQL

1. Log in to Supabase and create a new project in your target region (keep Vercel Function region close to this region for lowest latency).
2. Save your generated **Database Password** securely in a password manager.
3. Open **Project Settings -> Database -> Connect**:
   - Copy the **Transaction Pooler URI** (port `6543`, host ending in `.pooler.supabase.com`) for Vercel runtime (`DATABASE_URL`).
   - Copy the **Session Pooler URI** (port `5432`) or Direct Connection string for running Alembic migrations locally.
4. Format the runtime `DATABASE_URL` as:
   ```text
   postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres?sslmode=require
   ```
   *(The backend automatically normalizes `postgres://` or `postgresql://` prefixes to `postgresql+psycopg://` and enforces `sslmode=require` + `prepare_threshold=None` + `NullPool` on Supabase pooler endpoints.)*

---

## Step 3 — Apply Database Schema Migrations & Seed Initial Admin

> [!CAUTION]
> Always run Alembic migrations manually/explicitly from an authorized operator machine or controlled release step. Never auto-reset or drop production tables.

1. Temporarily point your local shell (or a temporary `.env`) to the Supabase **Session Pooler (port `5432`)** connection string:
   ```bash
   # Windows PowerShell example (do not store credentials in git files)
   $env:DATABASE_URL="postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"
   $env:INITIAL_ADMIN_EMAIL="<your-admin-email>"
   $env:INITIAL_ADMIN_PASSWORD="<strong-initial-admin-password>"
   ```
2. Run Alembic migrations to bring PostgreSQL up to head (`0008_saas_admin_subscriptions`):
   ```bash
   cd backend
   alembic -c alembic.ini current
   alembic -c alembic.ini upgrade head
   alembic -c alembic.ini current
   cd ..
   ```
3. Verify schema readiness and seed the initial platform administrator + default SaaS plan/settings:
   ```bash
   python backend/scripts/seed_admin.py
   ```
4. *(Optional)* Verify table list in Supabase SQL Editor (`admin_users`, `businesses`, `users`, `customers`, `products`, `invoices`, `invoice_items`, `payments`, `subscriptions`, `activation_codes`, `subscription_plans`, `notifications`, `admin_audit_logs`, `saas_settings`, `alembic_version`).

---

## Step 4 — Configure Supabase Storage (Private Bucket)

Vercel Functions run on a read-only code filesystem with ephemeral `/tmp`. Permanent logos, digital signatures, and PDFs **must** be persisted in Supabase Storage.

1. In Supabase Dashboard, go to **Storage -> New bucket**.
2. Name the bucket: `rmstorvix-private` *(or match `SUPABASE_STORAGE_BUCKET`)*.
3. Keep **Public bucket** toggled **OFF (Private)**. Private assets are streamed only by authenticated FastAPI endpoints after verifying `current_user.business_id` ownership (or via short-lived signed URLs).
4. Open **Project Settings -> API** and copy:
   - **Project URL** -> `SUPABASE_URL`
   - **service_role secret key** -> `SUPABASE_SERVICE_ROLE_KEY` *(server-only; never expose in browser code)*.

---

## Step 5 — Connect GitHub to Vercel & Configure Environment Variables

1. Log in to Vercel and click **Add New... -> Project**.
2. Import your GitHub repository (`rmstorvix-invoice-billing`).
   - **Framework Preset**: Other (Vercel automatically detects `vercel.json` + `api/index.py` Python runtime + root `requirements.txt`).
   - **Root Directory**: `./` (project root — **do not** set to `backend/`, because `api/index.py` and `vercel.json` live at repo root and bundle both `backend/**` and `frontend/**`).
3. Before clicking Deploy (or immediately before promoting), configure **Environment Variables** under **Project Settings -> Environment Variables** (for `Production` and `Preview` as needed):

| Variable | Recommended Value / Example | Notes |
|---|---|---|
| `APP_ENV` | `production` | Enforces `Secure` cookies cleanly |
| `APP_NAME` | `RMSTORVIX Invoice & Billing System` | Application title |
| `DEBUG` | `false` | Must stay `false` in production |
| `DATABASE_URL` | `postgresql+psycopg://postgres.<ref>:<pwd>@...pooler.supabase.com:6543/postgres?sslmode=require` | Supabase Transaction Pooler URI |
| `FRONTEND_URL` | `https://your-app.vercel.app` | Primary production origin |
| `ALLOWED_ORIGINS` | `https://your-app.vercel.app` | Comma-separated authorized origins |
| `CORS_ORIGINS` | `https://your-app.vercel.app` | Merged with `ALLOWED_ORIGINS` |
| `API_BASE_URL` | *(leave empty for same-origin)* | Only set if frontend & API use separate domains |
| `STORAGE_BACKEND` | `supabase` | Uses persistent Supabase Storage |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | From Supabase Project API settings |
| `SUPABASE_STORAGE_BUCKET` | `rmstorvix-private` | Private Storage bucket name |
| `SUPABASE_SERVICE_ROLE_KEY` | `<supabase-service-role-secret>` | Server-side secret only |
| `JWT_SECRET_KEY` | `<32+ char cryptographically random hex>` | Signing secret |
| `COOKIE_SECURE` | `true` | HTTPS-only cookies (`SameSite=lax`) |
| `COOKIE_SAMESITE` | `lax` | Use `none` only if split-domain HTTPS |
| `SESSION_COOKIE_NAME` | `inv_session` | User workspace cookie |
| `ADMIN_SESSION_COOKIE_NAME` | `rmx_admin_session` | Separate admin console cookie |
| `INITIAL_ADMIN_EMAIL` | `<admin-email>` | Initial seeded admin account |
| `INITIAL_ADMIN_PASSWORD` | `<initial-admin-password>` | Must be rotated on first `/admin` login |
| `SUPPORT_EMAIL` | `support@rmstorvix.com` | Shown on pending/expired gates |
| `SUPPORT_PHONE` | `<your-support-phone>` | Shown on pending/expired gates |
| `GSTIN_API_URL` | *(optional)* | External GSTIN provider URL |
| `GST_VERIFICATION_API_KEY` | *(optional)* | External GSTIN API key |
| `MAIL_CONFIGURATION` | *(optional)* | Future SMTP JSON/DSN placeholder |

4. Click **Deploy**. Future pushes to `main` on GitHub automatically trigger production Vercel deployments.

---

## Step 6 — Post-Deployment Production Verification Checklist

1. **Health Endpoint**: Open `https://<your-domain>/api/v1/health` -> verify `"status": "ok"` and `"database": "Database connection verified."`.
2. **Runtime Config**: Open `https://<your-domain>/app-config.js` -> verify `"appEnv": "production"` and zero leaked secrets.
3. **Admin Initial Login & Password Rotation**:
   - Visit `https://<your-domain>/admin`.
   - Sign in with `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`.
   - Complete the mandatory initial password change immediately.
   - Generate a test `RMX-XXXX-XXXX-XXXX` activation code cleanly or inspect KPIs.
4. **End-to-End Business Flow**:
   - Visit `https://<your-domain>/` -> verify Liquid Glass Login/Register page loads over HTTPS with Dark/Bright modes.
   - Register a test business -> verify account enters `PENDING_APPROVAL` + `NOT_ACTIVATED` and dashboard routes return `403`.
   - Approve + issue activation code from `/admin` -> redeem code on user portal -> verify Dashboard countdown & workspace unlock.
   - Upload a test **Business Logo** and **Digital Signature**, verify both persist across page reloads and appear inside a downloaded **Invoice PDF** (`/api/v1/invoices/{id}/pdf`).
   - Verify **Sidebar Drawer**, **Custom Invoice Themes**, **Customer / Product / Inventory / Payment / Report / CSV Export**, and **Permanent Delete** safeguards.

---

## Step 7 — Custom Domain, Backups & Monitoring

- **Custom Domain**: Add your domain in **Vercel Project -> Settings -> Domains**, update DNS `A`/`CNAME` records as instructed by Vercel, and update `FRONTEND_URL`, `ALLOWED_ORIGINS`, and `CORS_ORIGINS` to match `https://app.yourdomain.com`, then redeploy.
- **Database Backups & Recovery**:
  - Enable automated daily backups / Point-in-Time Recovery (PITR) in **Supabase Project -> Database -> Backups**.
  - Periodically verify backups by restoring into a Supabase branch or staging database and testing `alembic current`.
- **Logs & Error Monitoring**:
  - Inspect live serverless function logs in **Vercel Project -> Logs** (`vercel logs <deployment-url>`).
  - Inspect Postgres query performance and connection counts in **Supabase Project -> Reports / Logs**.
  - Review in-app governance trails in **Admin Panel -> Audit Logs** and **Notifications**.
