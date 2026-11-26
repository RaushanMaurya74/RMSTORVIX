# Local Setup & Verification Guide

## Prerequisites

- **Python 3.11+** (with `venv` and `pip`)
- **PostgreSQL 15+** (local installation or Docker container)

## 1. Create Environment Configuration

Copy `.env.example` to `.env` in the project root and set your local database credentials:

```powershell
Copy-Item .env.example .env
```

Review and update the PostgreSQL variables in `.env`:

- `POSTGRES_HOST` (default: `localhost`)
- `POSTGRES_PORT` (default: `5432`)
- `POSTGRES_DB` (default: `invoice_billing`)
- `POSTGRES_USER` (default: `invoice_app`)
- `POSTGRES_PASSWORD` (set a local development password)
- Optional: `DATABASE_URL` if you prefer a full SQLAlchemy connection URL override (e.g. `postgresql+psycopg://invoice_app:your_password@localhost:5432/invoice_billing`).

> Never commit `.env` or real credentials to version control.

## 2. Provision PostgreSQL Database

Connect to PostgreSQL as an admin user (for example `postgres`) and create the application role and database:

```sql
CREATE USER invoice_app WITH PASSWORD 'your_local_password';
CREATE DATABASE invoice_billing OWNER invoice_app;
```

## 3. Set Up Python Virtual Environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r backend\requirements.txt
```

## 4. Apply Database Migrations

From `backend/` (with `.venv` activated and PostgreSQL running):

```powershell
cd backend
alembic upgrade head
```

## 5. Run Automated Tests

Run the backend test suite from `backend/`:

```powershell
cd backend
pytest
```

## 6. Run the Application Server

From `backend/` (with `.venv` activated):

```powershell
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Then verify:

- Application shell: `http://127.0.0.1:8000/`
- Health check: `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/api/v1/health`
- Interactive OpenAPI docs: `http://127.0.0.1:8000/api/docs`

When PostgreSQL is reachable, `/health` returns HTTP `200` with `"status": "ok"` and `"database.status": "connected"`. When PostgreSQL is unreachable, `/health` returns HTTP `503` with `"status": "degraded"` without exposing database passwords or stack traces.
