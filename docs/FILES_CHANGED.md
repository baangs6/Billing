# Changed files

Local development branch: `codex/complete-billing-features`; baseline `c2333e7`. Existing untracked `output/` is excluded. Private `instance/` and disposable `tmp/` are ignored and must never be staged.

## Modified

- `README.md`
- `app.py`
- `factory_reset.py`
- `finance.py`
- `invoice_pdf.py`
- `mongo_store.py`
- `product_import.py`
- `saas.py`
- `sales_invoice_pdf.py`
- `scripts/backup_mongodb.py`
- `static/app.js`
- `static/premium.css`
- `templates/admin/auth.html`
- `templates/auth.html`
- `templates/base.html`
- `templates/billing.html`
- `templates/customers.html`
- `templates/finance.html`
- `templates/home.html`
- `templates/invoice.html`
- `templates/payments.html`
- `templates/products.html`
- `templates/proposal.html`
- `templates/proposal_form.html`
- `templates/proposals.html`
- `templates/reports.html`
- `templates/reset_sections.html`
- `templates/settings.html`
- `tests/admin_visual_review.py`
- `tests/proposal_visual_review.py`
- `tests/test_app.py`
- `tests/visual_review.py`

## Added

- `accounting_reports.py`
- `accounts.py`
- `company_profile.py`
- `docs/CAPABILITY_MAP.md`
- `docs/FEATURE_PROGRESS.md`
- `docs/FILES_CHANGED.md`
- `docs/IMPLEMENTATION_REVIEW.md`
- `docs/REVIEW_LOG.md`
- `docs/SPEC-product-stock-extensions.md`
- `docs/VERIFICATION.md`
- `party_data.py`
- `product_media.py`
- `product_units.py`
- `scripts/prepare_trade.py`
- `scripts/verify_backup.py`
- `static/purchases.js`
- `templates/account_picker.html`
- `templates/accounting_reports.html`
- `templates/accounts.html`
- `templates/business_profile.html`
- `templates/party_import.html`
- `templates/purchase_detail.html`
- `templates/purchases.html`
- `templates/sales_returns.html`
- `templates/supplier_ledger.html`
- `templates/suppliers.html`
- `tests/conftest.py`
- `tests/test_extended.py`
- `tests/test_harness.py`
- `tests/test_product_units.py`
- `tests/test_trade.py`
- `trade.py`

## Persistent storage

New optional tenant fields only, plus nine additive collections and a partial payment submission index. See IMPLEMENTATION_REVIEW.md for index, activation, backup and rollback constraints. No live application data migration, push or deployment has been performed.
