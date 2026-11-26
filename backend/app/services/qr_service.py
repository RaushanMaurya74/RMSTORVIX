"""UPI payment URI and amount-specific QR code generation service."""

from decimal import Decimal
import io
from urllib.parse import urlencode

from fastapi import HTTPException, status
import qrcode
from sqlalchemy.orm import Session

from app.models.business import Business
from app.models.invoice import Invoice
from app.services.invoice_service import get_owned_invoice


def build_upi_payment_uri(business: Business | None, invoice: Invoice) -> str | None:
    """Build an amount-specific UPI payment URI when UPI is configured and balance is due."""
    if business is None or not business.upi_id:
        return None
    if invoice.status in {"draft", "void"} or invoice.balance_due <= Decimal("0.00"):
        return None

    payee_name = (business.bank_account_holder or business.name or "Business").strip()
    params = urlencode(
        {
            "pa": business.upi_id.strip(),
            "pn": payee_name[:80],
            "am": f"{invoice.balance_due:.2f}",
            "cu": invoice.currency_code,
            "tn": f"Invoice {invoice.invoice_number}",
        }
    )
    return f"upi://pay?{params}"


def generate_qr_png_bytes(payload: str) -> bytes:
    """Render a crisp PNG QR code from a payment URI."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#172033", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def get_invoice_qr_png(db: Session, *, business_id: int, invoice_id: int) -> bytes:
    """Return PNG QR bytes for an owned unpaid issued invoice."""
    invoice = get_owned_invoice(db, business_id=business_id, invoice_id=invoice_id)
    uri = build_upi_payment_uri(invoice.business, invoice)
    if not uri:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment QR code is unavailable for this invoice.",
        )
    return generate_qr_png_bytes(uri)
