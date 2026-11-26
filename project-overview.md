# Invoice & Billing System

## Overview
Build a web-based invoicing and billing application for small businesses to manage customers, products/services, create invoices with tax calculations, track payments and generate downloadable/printable PDF invoices.

## Goals
1. Allow authenticated users to manage customers and product/service records.
2. Create, review, issue and retrieve invoices with server-calculated totals.
3. Track payment status and provide basic sales/invoice summaries.
4. Generate PDFs securely and maintain a meaningful audit trail.
5. Provide a usable responsive interface.

## Core User Flow
1. User signs in.
2. User configures business details.
3. User adds customers and products/services.
4. User creates an invoice and selects customer and line items.
5. Server validates quantities, prices, tax rules and totals; invoice is saved transactionally.
6. User views, prints or downloads the PDF through an authorized flow.
7. User records payments and views reports.

## Features
### Authentication and Business Profile
- Registration/sign-in, sign-out and protected pages.
- Business name, contact details and invoice profile settings.

### Customers and Products
- Create, read, update and delete customer records.
- Manage product/service name, description, price and applicable tax configuration.
- Search, filter and paginate where needed.

### Invoices
- Create and edit draft invoices.
- Add line items, quantity, unit price, discount (if enabled) and tax.
- Server-side totals and validation.
- Invoice statuses such as draft, issued, paid, partially paid and overdue, subject to defined rules.
- Invoice detail page and PDF output.

### Payments and Reports
- Record payment entries and payment dates/methods.
- Basic sales and invoice summaries, date filters and export options where defined.

### Security and Audit
- Authenticated access, record ownership checks, secure PDF delivery and audit events for important actions.

## Scope
### In Scope
- Core customer/product/invoice/payment workflows.
- GST/tax configuration and calculations, after requirements are clarified.
- PDF invoice generation.
- Basic reports and audit trail.
- Tests and setup documentation.

### Out of Scope Initially
- Live payment gateway integrations.
- Complex accounting ledger, payroll, inventory/warehouse management.
- E-invoicing or government portal integrations unless separately specified.
- Mobile native applications.

## Success Criteria
1. User can register/sign in and securely manage their own business records.
2. User can create an invoice with customer and line items; totals are server-validated and saved.
3. Invoice can be viewed and a PDF can be generated and accessed only by authorized users.
4. Payments and invoice status are recorded consistently.
5. Automated tests cover key calculation, validation and authorization cases.
6. Project setup and usage instructions are documented.
