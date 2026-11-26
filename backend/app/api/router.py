"""Versioned API router aggregation."""

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.business import router as business_router
from app.api.customers import router as customers_router
from app.api.health import router as health_router
from app.api.invoices import router as invoices_router
from app.api.payments import router as payments_router
from app.api.products import router as products_router
from app.api.reports import router as reports_router
from app.api.subscription import router as subscription_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(subscription_router)
api_router.include_router(business_router)
api_router.include_router(customers_router)
api_router.include_router(products_router)
api_router.include_router(invoices_router)
api_router.include_router(payments_router)
api_router.include_router(reports_router)
api_router.include_router(admin_router)
