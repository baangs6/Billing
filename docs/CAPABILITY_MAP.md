# Capability map

| Module | Responsibility | Dependencies |
|---|---|---|
| foundation | Tenant access, snapshots, backup verification, audit, settings | existing app |
| parties | Customer extensions, suppliers, imports, balances | foundation |
| purchasing | Orders, receipts, returns, supplier payments | parties, existing inventory |
| sales-documents | Proforma, challans, credit notes, returns | parties, existing billing |
| treasury | Named accounts, transfers, reconciliation | purchasing, sales-documents, finance |
| printing | Print formats, columns, QR, historical snapshots | existing invoices |
| reporting | Reconciled sales, purchase, stock, tax and party reports | purchasing, sales-documents, treasury |
| integrations | Consent, outbox, provider configuration, delivery status | reporting |

Build order follows the table, with printing independent of purchasing. Existing routes and collections remain authoritative. Money stays integer paise, quantities integer thousandths. New business writes must use the existing serialized per-company transaction; all reads and references are tenant scoped. Existing protected company admins gain only the explicitly added module permissions; other roles require explicit assignment. No new features bypass plan inventory/GST/PDF/report restrictions.

Verification: python -m pytest -q; node --check on changed JS; browser flows against disposable ledger_test databases; PDF rendering. Tests must never target the configured business database. Production schema preparation requires a verified private backup and explicit approval. No live migrations or startup backfills.
