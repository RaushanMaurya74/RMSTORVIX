"""Server-side invoice PDF generation with business logo, custom themes, HSN, GST split, and UPI QR."""

from datetime import datetime, timezone
from decimal import Decimal
import io
from pathlib import Path
import re

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.invoice import Invoice
from app.models.user import User
from app.services.audit_service import record_audit_event
from app.services.invoice_service import compute_effective_status, get_owned_invoice
from app.services.logo_service import load_logo_png_for_pdf
from app.services.qr_service import build_upi_payment_uri, generate_qr_png_bytes
from app.services.signature_service import load_signature_png_for_pdf
from app.services.storage_service import get_stored_bytes, put_stored_bytes
from app.services.theme_service import (
    contrast_text_rgb,
    hex_to_rgb,
    muted_rgb,
    resolve_business_theme,
)

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _pdf_text(value: str | None) -> str:
    """Normalize text for built-in PDF Helvetica encoding without crashing on Unicode."""
    if not value:
        return ""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2022": "*",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u20b9": "INR ",
        "\u20ac": "EUR ",
        "\u00a3": "GBP ",
    }
    normalized = value
    for src, target in replacements.items():
        normalized = normalized.replace(src, target)
    return normalized.encode("latin-1", "replace").decode("latin-1")


def _fmt_money(amount: Decimal, currency_code: str) -> str:
    return f"{currency_code} {amount:,.2f}"


def _safe_pdf_path(base_dir: Path, storage_key: str) -> Path:
    """Resolve storage_key inside base_dir and guard against path traversal."""
    base_resolved = base_dir.resolve()
    target = (base_resolved / storage_key).resolve()
    if base_resolved != target and base_resolved not in target.parents:
        raise ValueError("Invalid PDF storage path.")
    return target


def _luminance(rgb: tuple[int, int, int]) -> float:
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0


def _pick_accent_on_bg(
    accent_rgb: tuple[int, int, int],
    bg_hex: str,
    fallback_rgb: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Ensure accent text stays readable over custom header/card background fills."""
    bg_lum = _luminance(hex_to_rgb(bg_hex))
    acc_lum = _luminance(accent_rgb)
    if abs(bg_lum - acc_lum) < 0.28:
        return fallback_rgb
    return accent_rgb


def render_invoice_pdf_bytes(invoice: Invoice) -> bytes:
    """Render a themed invoice PDF with optional business logo, HSN, GST split, QR, and signature."""
    business = invoice.business
    customer = invoice.customer
    effective_status = compute_effective_status(invoice).upper().replace("_", " ")

    theme = resolve_business_theme(business)
    primary_rgb = hex_to_rgb(theme["primary_color"], "#2563EB")
    secondary_rgb = hex_to_rgb(theme["secondary_color"], "#1E40AF")
    accent_rgb = hex_to_rgb(theme["accent_color"], "#EFF6FF")
    header_rgb = hex_to_rgb(theme["header_color"], "#F8FAFC")
    table_hdr_rgb = hex_to_rgb(theme["table_header_color"], "#EFF6FF")
    text_rgb = hex_to_rgb(theme["text_color"], "#172033")
    border_rgb = hex_to_rgb(theme["border_color"], "#E2E8F0")

    body_muted_rgb = muted_rgb(text_rgb, factor=0.4)
    header_text_rgb = contrast_text_rgb(theme["header_color"], theme["text_color"])
    header_muted_rgb = (
        (226, 232, 240)
        if _luminance(header_rgb) < 0.54
        else muted_rgb(header_text_rgb, factor=0.35)
    )
    header_title_rgb = _pick_accent_on_bg(primary_rgb, theme["header_color"], header_text_rgb)
    table_hdr_text_rgb = contrast_text_rgb(theme["table_header_color"], theme["text_color"])
    accent_text_rgb = contrast_text_rgb(theme["accent_color"], theme["text_color"])
    accent_title_rgb = _pick_accent_on_bg(primary_rgb, theme["accent_color"], accent_text_rgb)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()

    # Themed Header Banner Container
    biz_lines = [
        business.legal_name,
        business.address_line1,
        business.address_line2,
        ", ".join(
            part
            for part in [business.city, business.state, business.postal_code]
            if part
        )
        or None,
        business.country,
        f"Email: {business.email}" if business.email else None,
        f"Phone: {business.phone}" if business.phone else None,
        f"Tax / GSTIN: {business.tax_id}" if business.tax_id else None,
    ]
    left_lines = [line for line in biz_lines if line]

    gst_label = "IGST" if invoice.gst_type == "igst" else "CGST + SGST"
    right_lines = [
        f"Invoice #: {invoice.invoice_number}",
        f"Status: {effective_status}",
        f"Issue Date: {invoice.issue_date.isoformat()}",
        f"Due Date: {invoice.due_date.isoformat()}",
        f"GST Mode: {gst_label}",
        f"Currency: {invoice.currency_code}",
    ]

    logo_data = load_logo_png_for_pdf(business)
    logo_draw_w = 0.0
    logo_draw_h = 0.0
    if logo_data is not None:
        _, px_w, px_h = logo_data
        scale = min(28.0 / max(px_w, 1), 15.0 / max(px_h, 1))
        logo_draw_w = round(px_w * scale, 2)
        logo_draw_h = round(px_h * scale, 2)

    max_rows = max(len(left_lines), len(right_lines))
    content_rows_h = 9.0 + max_rows * 4.8 + 4.0
    header_h = max(content_rows_h + 6.0, (logo_draw_h + 12.0) if logo_data else 0.0)
    header_y = 14.0

    pdf.set_fill_color(*header_rgb)
    pdf.set_draw_color(*border_rgb)
    pdf.rect(14.0, header_y, 182.0, header_h, style="DF")

    # Top theme primary accent strip
    pdf.set_fill_color(*primary_rgb)
    pdf.rect(14.0, header_y, 182.0, 2.0, style="F")

    left_text_x = 18.0
    if logo_data is not None:
        logo_png, _, _ = logo_data
        pdf.image(io.BytesIO(logo_png), x=18.0, y=header_y + 5.0, w=logo_draw_w, h=logo_draw_h)
        left_text_x = 18.0 + logo_draw_w + 4.0

    left_col_w = max(60.0, 126.0 - left_text_x)
    pdf.set_xy(left_text_x, header_y + 4.5)
    pdf.set_text_color(*header_text_rgb)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(left_col_w, 8, _pdf_text(business.name)[:38], new_x=XPos.RIGHT, new_y=YPos.TOP)

    pdf.set_xy(130.0, header_y + 4.5)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*header_title_rgb)
    pdf.cell(62.0, 8, "INVOICE", align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 8.8)
    for i in range(max_rows):
        row_y = header_y + 13.0 + i * 4.8
        left_txt = _pdf_text(left_lines[i]) if i < len(left_lines) else ""
        right_txt = _pdf_text(right_lines[i]) if i < len(right_lines) else ""
        pdf.set_xy(left_text_x, row_y)
        pdf.set_text_color(*header_muted_rgb)
        pdf.cell(left_col_w, 4.8, left_txt[:56])

        pdf.set_xy(126.0, row_y)
        pdf.set_text_color(*header_text_rgb if i == 0 else header_muted_rgb)
        pdf.cell(66.0, 4.8, right_txt, align="R")

    pdf.set_y(header_y + header_h + 6.0)

    # Bill To block
    pdf.set_text_color(*secondary_rgb)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "BILL TO", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "", 9.3)
    cust_lines = [
        customer.name,
        customer.company_name,
        customer.address_line1,
        customer.address_line2,
        ", ".join(
            part
            for part in [customer.city, customer.state, customer.postal_code]
            if part
        )
        or None,
        customer.country,
        f"Email: {customer.email}" if customer.email else None,
        f"Phone: {customer.phone}" if customer.phone else None,
        f"Tax ID / GSTIN: {customer.tax_id}" if customer.tax_id else None,
    ]
    for idx, line in enumerate(line for line in cust_lines if line):
        pdf.set_text_color(*(text_rgb if idx == 0 else body_muted_rgb))
        pdf.set_font("Helvetica", "B" if idx == 0 else "", 9.3)
        pdf.set_x(14.0)
        pdf.multi_cell(182.0, 4.9, _pdf_text(line), align="L")

    pdf.ln(5)

    # Line items table header (sum = 182mm across A4 printable width)
    col_widths = [54, 20, 18, 26, 16, 20, 28]
    headers = ["Item", "HSN", "Qty", "Unit Price", "Disc %", "GST %", "Line Total"]

    def _render_table_header() -> None:
        pdf.set_fill_color(*table_hdr_rgb)
        pdf.set_draw_color(*border_rgb)
        pdf.set_text_color(*table_hdr_text_rgb)
        pdf.set_font("Helvetica", "B", 8.5)
        for idx, heading in enumerate(headers):
            align = "L" if idx in (0, 1) else "R"
            pdf.cell(col_widths[idx], 8, heading, border="TB", align=align, fill=True)
        pdf.ln()

    _render_table_header()

    # Line items rows with clean multi-page overflow support
    pdf.set_font("Helvetica", "", 8.5)
    for item in invoice.items:
        row_needed = 13.0 if item.description else 8.0
        if pdf.get_y() + row_needed > 268.0:
            pdf.add_page()
            _render_table_header()
            pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*text_rgb)
        pdf.set_draw_color(*border_rgb)
        label = item.item_name
        if item.unit:
            label = f"{label} ({item.unit})"
        pdf.cell(col_widths[0], 7, _pdf_text(label)[:32], border="B", align="L")
        pdf.cell(col_widths[1], 7, _pdf_text(item.hsn_code or "-")[:10], border="B", align="L")
        pdf.cell(col_widths[2], 7, f"{item.quantity:.2f}", border="B", align="R")
        pdf.cell(
            col_widths[3],
            7,
            _pdf_text(_fmt_money(item.unit_price, invoice.currency_code)),
            border="B",
            align="R",
        )
        pdf.cell(col_widths[4], 7, f"{item.discount_percent:.2f}%", border="B", align="R")
        pdf.cell(col_widths[5], 7, f"{item.tax_rate:.2f}%", border="B", align="R")
        pdf.cell(
            col_widths[6],
            7,
            _pdf_text(_fmt_money(item.line_total, invoice.currency_code)),
            border="B",
            align="R",
        )
        pdf.ln()
        if item.description:
            pdf.set_font("Helvetica", "", 7.5)
            pdf.set_text_color(*body_muted_rgb)
            pdf.multi_cell(col_widths[0] + col_widths[1], 4.5, _pdf_text(item.description))
            pdf.set_font("Helvetica", "", 8.5)

    pdf.ln(5)

    # Totals summary box aligned right with theme accent background
    summary_rows: list[tuple[str, str, bool]] = [
        ("Subtotal", _fmt_money(invoice.subtotal_amount, invoice.currency_code), False),
        ("Discount", _fmt_money(invoice.discount_amount, invoice.currency_code), False),
    ]
    if invoice.gst_type == "igst":
        summary_rows.append(
            ("IGST", _fmt_money(invoice.igst_amount, invoice.currency_code), False)
        )
    else:
        summary_rows.append(
            ("CGST", _fmt_money(invoice.cgst_amount, invoice.currency_code), False)
        )
        summary_rows.append(
            ("SGST", _fmt_money(invoice.sgst_amount, invoice.currency_code), False)
        )
    summary_rows.extend(
        [
            ("Total Tax", _fmt_money(invoice.tax_amount, invoice.currency_code), False),
            ("Grand Total", _fmt_money(invoice.total_amount, invoice.currency_code), True),
            ("Amount Paid", _fmt_money(invoice.amount_paid, invoice.currency_code), False),
            ("Balance Due", _fmt_money(invoice.balance_due, invoice.currency_code), True),
        ]
    )

    totals_box_h = len(summary_rows) * 6.2 + 4.0
    if pdf.get_y() + totals_box_h > 272:
        pdf.add_page()
    totals_top_y = pdf.get_y()
    pdf.set_fill_color(*accent_rgb)
    pdf.set_draw_color(*border_rgb)
    pdf.rect(112.0, totals_top_y, 84.0, totals_box_h, style="DF")

    pdf.set_y(totals_top_y + 2.0)
    for label, val, is_bold in summary_rows:
        pdf.set_x(115.0)
        pdf.set_font("Helvetica", "B" if is_bold else "", 9.2)
        pdf.set_text_color(*(accent_title_rgb if is_bold else accent_text_rgb))
        pdf.cell(38.0, 6.2, label, align="L", new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(40.0, 6.2, _pdf_text(val), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(totals_top_y + totals_box_h)

    # Bank Details & Amount-Specific Payment QR Code
    bank_lines = [
        f"Account Holder: {business.bank_account_holder}" if business.bank_account_holder else None,
        f"Bank Name: {business.bank_name}" if business.bank_name else None,
        f"Account Number: {business.bank_account_number}" if business.bank_account_number else None,
        f"IFSC Code: {business.bank_ifsc_code}" if business.bank_ifsc_code else None,
        f"Branch: {business.bank_branch}" if business.bank_branch else None,
        f"UPI ID: {business.upi_id}" if business.upi_id else None,
    ]
    bank_lines = [line for line in bank_lines if line]
    payment_uri = build_upi_payment_uri(business, invoice)

    if bank_lines or payment_uri:
        needed_h = max(len(bank_lines) * 4.8 + 8.0, 40.0 if payment_uri else 0.0)
        if pdf.get_y() + needed_h > 272:
            pdf.add_page()
        pdf.ln(5)
        pdf.set_draw_color(*border_rgb)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(4)

        section_top_y = pdf.get_y()
        if bank_lines:
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*secondary_rgb)
            pdf.cell(125, 5.5, "Bank & Payment Details", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 8.8)
            pdf.set_text_color(*body_muted_rgb)
            for line in bank_lines:
                pdf.cell(125, 4.8, _pdf_text(line), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if payment_uri:
            qr_bytes = generate_qr_png_bytes(payment_uri)
            qr_x = 160
            qr_y = section_top_y
            pdf.image(io.BytesIO(qr_bytes), x=qr_x, y=qr_y, w=32, h=32)
            pdf.set_xy(qr_x - 4, qr_y + 33)
            pdf.set_font("Helvetica", "B", 7.8)
            pdf.set_text_color(*text_rgb)
            pdf.cell(
                40,
                4.5,
                _pdf_text(f"Scan & Pay {_fmt_money(invoice.balance_due, invoice.currency_code)}"),
                align="C",
            )
            pdf.set_y(max(pdf.get_y(), qr_y + 39))

    if invoice.notes or invoice.terms:
        pdf.ln(4)
        pdf.set_draw_color(*border_rgb)
        pdf.line(14, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(4)

        if invoice.notes:
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*secondary_rgb)
            pdf.cell(0, 5.5, "Notes", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*body_muted_rgb)
            pdf.multi_cell(0, 5, _pdf_text(invoice.notes))
            pdf.ln(2)

        if invoice.terms:
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(*secondary_rgb)
            pdf.cell(0, 5.5, "Payment Terms", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*body_muted_rgb)
            pdf.multi_cell(0, 5, _pdf_text(invoice.terms))

    # Authorized Visual Signature Section (respecting aspect ratio and placement)
    sig_data = load_signature_png_for_pdf(business)
    if sig_data is not None:
        sig_png, px_w, px_h = sig_data
        max_w_mm = 45.0
        max_h_mm = 18.0
        scale = min(max_w_mm / max(px_w, 1), max_h_mm / max(px_h, 1))
        draw_w = round(px_w * scale, 2)
        draw_h = round(px_h * scale, 2)

        block_height = draw_h + 15.0
        if pdf.get_y() + block_height > 272:
            pdf.add_page()

        pdf.ln(6)
        placement = business.signature_placement or "bottom_right"
        box_w = 54.0
        if placement == "bottom_left":
            block_x = 14.0
            align_mode = "L"
        elif placement == "bottom_center":
            block_x = (210.0 - box_w) / 2.0
            align_mode = "C"
        else:
            block_x = 196.0 - box_w
            align_mode = "R"

        if align_mode == "L":
            img_x = block_x
        elif align_mode == "C":
            img_x = block_x + (box_w - draw_w) / 2.0
        else:
            img_x = block_x + (box_w - draw_w)

        pdf.set_xy(block_x, pdf.get_y())
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*body_muted_rgb)
        pdf.cell(
            box_w,
            4.5,
            _pdf_text(f"For {business.name}"),
            align=align_mode,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

        img_y = pdf.get_y() + 1.0
        pdf.image(io.BytesIO(sig_png), x=img_x, y=img_y, w=draw_w, h=draw_h)
        pdf.set_xy(block_x, img_y + draw_h + 1.5)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*text_rgb)
        pdf.cell(box_w, 4.5, "Authorized Signatory", align=align_mode, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    return bytes(pdf.output())


def refresh_stored_invoice_pdf(
    db: Session,
    *,
    invoice: Invoice,
    settings: Settings | None = None,
) -> None:
    """Regenerate and overwrite the managed PDF file after invoice updates."""
    active_settings = settings or get_settings()
    safe_num = _SAFE_FILENAME_RE.sub("_", invoice.invoice_number).strip("_") or f"inv_{invoice.id}"
    storage_key = f"biz_{invoice.business_id}/invoice_{invoice.id}_{safe_num}.pdf"

    pdf_bytes = render_invoice_pdf_bytes(invoice)
    put_stored_bytes(
        namespace="pdfs",
        base_dir=active_settings.resolved_pdf_dir,
        storage_key=storage_key,
        data=pdf_bytes,
        content_type="application/pdf",
        asset_label="pdf",
        settings=active_settings,
    )
    invoice.pdf_storage_key = storage_key
    invoice.pdf_generated_at = datetime.now(timezone.utc)
    db.commit()


def generate_and_store_invoice_pdf(
    db: Session,
    *,
    current_user: User,
    invoice_id: int,
    settings: Settings | None = None,
) -> tuple[bytes, str]:
    """Generate/retrieve a business-owned invoice PDF inside managed or cloud storage."""
    active_settings = settings or get_settings()
    invoice = get_owned_invoice(
        db, business_id=current_user.business_id, invoice_id=invoice_id
    )

    safe_num = _SAFE_FILENAME_RE.sub("_", invoice.invoice_number).strip("_") or f"inv_{invoice.id}"
    download_filename = f"{safe_num}.pdf"
    storage_key = f"biz_{invoice.business_id}/invoice_{invoice.id}_{safe_num}.pdf"
    base_dir = active_settings.resolved_pdf_dir

    cached_bytes = (
        get_stored_bytes(
            namespace="pdfs",
            base_dir=base_dir,
            storage_key=storage_key,
            asset_label="pdf",
            settings=active_settings,
        )
        if invoice.pdf_storage_key == storage_key
        else None
    )

    if cached_bytes is not None:
        pdf_bytes = cached_bytes
    else:
        pdf_bytes = render_invoice_pdf_bytes(invoice)
        put_stored_bytes(
            namespace="pdfs",
            base_dir=base_dir,
            storage_key=storage_key,
            data=pdf_bytes,
            content_type="application/pdf",
            asset_label="pdf",
            settings=active_settings,
        )
        invoice.pdf_storage_key = storage_key
        invoice.pdf_generated_at = datetime.now(timezone.utc)

    record_audit_event(
        db,
        business_id=current_user.business_id,
        user_id=current_user.id,
        action="invoice.pdf_downloaded",
        entity_type="invoice",
        entity_id=invoice.id,
        details={"invoice_number": invoice.invoice_number},
    )
    db.commit()

    return pdf_bytes, download_filename
