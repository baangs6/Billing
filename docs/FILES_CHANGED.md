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
- `templates/inventory.html`
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
- `docs/NAVIGATION_MERGE.md`
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
- `templates/finance_tabs.html`
- `templates/party_import.html`
- `templates/purchase_detail.html`
- `templates/purchases.html`
- `templates/report_controls.html`
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

Nine additive collections and a partial payment submission index were previously activated with explicit approval. The navigation consolidation requires no data migration. See IMPLEMENTATION_REVIEW.md and NAVIGATION_MERGE.md for activation and verification details. Nothing has been pushed or deployed to Render.


## Invoice creation follow-up

Additional files: `billing_options.py`, `static/billing-options.js`, `templates/billing_bank_popup.html`, `tests/test_billing_options.py`, `tests/test_billing_workflow.py`, `tests/test_thermal_layouts.py`, and `docs/BILLING_WORKFLOW.md`. Existing billing, account, report, PDF and profile modules/templates were extended in place. No schema migration is needed; no old business records are rewritten.
