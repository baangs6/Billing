# Integrated development review

This branch is a reviewed development increment, not a claim that the entire master checklist is complete. FEATURE_PROGRESS.md records every supplied feature separately, including unimplemented work. User-approved additive Atlas preparation and local service restart were completed on 18 October 2026. GitHub push and Render deployment remain unapproved and were not performed.

## Preserved behavior

Flask/Jinja UI, MongoDB Atlas, company IDs, user/session authentication, owner TOTP admin service, plan approval/renewal, existing role checks, invoice numbering, Non-GST default, product imports and optional SKU/purchase price, customer popup, common invoice discount/additional charges/round-off, saved snapshots, invoice/payment edits, recoverable invoice Trash, proposals, finance receipts, service reminders and password-confirmed resets remain in place. Existing tests were not deleted or weakened.

## New development modules

- Suppliers: separate tenant-scoped records; profile fields, archive/search, opening balances, ledgers and statements.
- Products: optional wholesale rates, inclusive/exclusive defaults, nonstock service classification, primary/alternate units and exact default rate conversion. Physical stock is primary-unit thousandths; document lines retain displayed quantities and immutable conversion fields. Bounded private product thumbnails are excluded from picker payloads. Basic edits preserve advanced fields.
- Parties: added customer contact/PAN/shipping/category/bank/credit terms, bounded opening settlements and credit-limit checks. CSV/XLSX import checks the complete file first; at most 4000 parties, 5 MB, batches of 200 within one transaction. A submission token prevents repeated imports.
- Purchasing: multi-line supplier invoices, original supplier references, inclusive/exclusive GST, common discount and optional rounding, source-linked payments, partial purchase-order receipts, purchase returns/debit notes, supplier credits/refunds, PDFs and payables.
- Sales documents: proforma and delivery-challan types reuse proposals. Challan dispatch changes stock once; dispatch cancellation restores it; conversion verifies dispatched product quantities and avoids a second stock deduction.
- Sales returns: original-line quantities, cumulative original tax/amount allocation, credit-note PDFs, bounded refunds and adjusted customer balances. Credited invoices and refunded payment histories are protected against incompatible edits/cancellation.
- Cash/bank: named accounts, details/openings, source-derived receipt/payment/refund/expense ledgers and balanced internal transfers. Overdraw checks consider subsequent recorded dates. Existing unassigned entries remain in legacy Cash/Bank/Other accounts.
- Profile/printing: extra legal/business header fields, GST registration selection, A4 grid variants, original A5, 58/80 mm content-sized thermal PDFs, GST-column/description/time options, signature box, bank/UPI visibility and optional QR. Preferences are copied into new invoice snapshots.
- Management reporting: purchase, receivables/payables, credit/debit notes, HSN, tax breakdown and current catalog-cost stock valuation; manual CSV/XLSX/PDF exports. These are not statutory filing returns.
- Safety: linked reset requirements cover new records; backup captures all application collections plus validators/indexes, and isolated restore verification checks document equality and recreates metadata.

## Storage and activation

Additive collections: suppliers, purchases, purchase_orders, trade_payments, trade_returns, party_imports, sales_returns, bank_accounts, account_transfers. Each has a tenant index, numeric ID index/counter, and (except suppliers) a unique tenant/submission index. A partial unique tenant/submission index is added to existing payments for new browser payment tokens. Legacy tokenless callers remain compatible. No existing tenant records are backfilled, renamed or deleted. Company/party extra fields and optional invoice/proposal fields are additive. Existing money stays integer paise and quantities integer thousandths.

New permissions: supplier.view, supplier.manage, purchase.view, purchase.manage, return.manage. Existing protected company administrators receive these at access evaluation without rewriting role records. Other roles must be explicitly granted permissions. Purchasing requires the current inventory plan feature; GST/PDF/report/export restrictions remain server-side.

The service does not automatically prepare the new schemas. New navigation stays hidden and protected endpoints return setup-pending until preparation exists. Do not deploy and accidentally rely on runtime collection creation.

After explicit user approval, an operator should create and verify a fresh private backup, then run:

```powershell
python scripts/backup_mongodb.py
python scripts/verify_backup.py
python scripts/prepare_trade.py
python scripts/prepare_trade.py --apply --backup "ABSOLUTE_PATH_TO_THE_VERIFIED_ATLAS_JSON"
```

The third command is read-only dry run. The final command verifies the manifest SHA-256 and selected database identity, then prepares only additive storage. It must not be run without approval. Backups and verification manifests remain under ignored instance/backups; they contain private data and must never be committed or shared publicly.

Restore verification succeeded against a disposable ledger_restore_test database: 38 collection exports (including currently empty proposed collections), 570 documents, plus original validators/indexes. Manifest SHA-256: 901b9a96d7f914cf0a9bc82262f6e695744dcf3bbd7b5bdee12607fa270fdfbf. No new financial records were written to the configured business database. A backup is not a zero-data-loss rollback for writes made after its timestamp.

After activation, prefer reviewed roll-forward repairs. Prior code does not understand purchase/refund ledgers; reverting code after posting documents can hide financial activity. Freeze writes and prepare a fresh backup before any recovery. Do not drop new collections to roll back.

## Security review

Trust boundaries checked: tenant route parameters, JSON items, uploaded spreadsheets, account/supplier/product IDs, financial amounts and generated exports. New routes use the existing authenticated tenant store and company-serialized MongoDB transaction wrapper. All foreign-key lookups use owned/scoped operations. CSRF and subscription state checks run before business writes; submission indexes and transaction locks protect retries/concurrency. Uploads are bounded; spreadsheet formulas/unknown headers are rejected, XLSX zip expansion is limited, exports escape spreadsheet formula prefixes, HTML uses autoescape and PDF text is escaped. No new external HTTP calls or credentials were introduced.

Opening balances become immutable once invoice/purchase or settlement history exists. Incompatible reset selections fail before deletion. Backup content is private; no password hashes or connection strings are committed. Unverified SOC2/IRN/filing marketing assertions were removed from existing screens.

Limits: GSTIN validation is structural, not registration/checksum verification. No independent penetration test or deployment configuration audit was performed. Verify HTTPS=1, stable SECRET_KEY, Atlas network rules/least-privilege user and private backup access in the deployment environment. Dependency vulnerability scanning, physical printers and real payment-app QR scanning are not verified.

## External services and unfinished work

SMTP remains unconfigured, as previously confirmed by the user. WhatsApp/SMS delivery needs a legitimate provider, approved sender/templates, credentials kept in server secrets, per-party consent, retry/outbox implementation and a durable scheduler. No external messages are sent. GST lookup/filing/reconciliation, OCR, product-library data and online-store integration are absent. Native apps and installable PWA are not built.

Not-implemented internal work is explicitly listed in FEATURE_PROGRESS.md: advanced batch/serial/IMEI stock, default/per-item product discount configuration, arbitrary invoice columns/placement, bank-statement reconciliation, tax-aware expenses/ITC, standalone value-only credit adjustments, multi-business identity migration, complete self-service backup/restore, statutory subscription tax invoices and automatic year close. TDS/TCS/year close need agreed business-specific accounting rules; identity and existing stock tracking changes need migration review and source data. These are not falsely reported as complete.

## Operation

1. Grant the relevant role permissions; Company Admin has them automatically. Existing plans still control inventory, GST, PDF and reports.
2. Suppliers -> Add supplier -> set opening balance/credit terms. View Ledger for statements and opening settlements.
3. Purchases -> Purchase orders -> create an order. Receive items in partial quantities; received source lines are bounded. Direct purchases are also supported.
4. Open a posted purchase to add payment, enter a full/partial return, download debit note, or record refund against supplier credit. Posted purchases are immutable.
5. Proposals -> New -> choose Quotation, Proforma or Delivery challan. Dispatch a challan from its detail page; review conversion to invoice. Dispatched quantities cannot silently change.
6. Invoice -> Returns & credit notes -> choose quantities and reason. Record a refund only when credit is available. The customer ledger and original invoice balance reconcile these records.
7. Cash & banks -> create named accounts, choose accounts on new settlements/expenses, and record internal transfers. Existing entries are not automatically reassigned.
8. Settings -> Additional profile & invoice printing -> choose preferences. New invoices snapshot them; existing PDFs retain saved preferences.
9. Products -> configure an alternate unit and primary units per alternate (for example BOX = 10 PCS). Select units and retail/wholesale prices on billing. A service has no physical stock. Primary unit/type changes are blocked once stock or history exists. Upload PNG/JPEG photos up to 2 MB; decoded thumbnails are private. Rates support at most nine meaningful decimal places; quantities must map exactly to primary thousandths. Receive purchase orders in their original unit.
10. Reports -> Purchases, GST, ledgers & valuation -> select dates and export. Receivables/payables use the To date; valuation is current catalog cost, not historical FIFO/weighted average.

## Verification record

- Baseline original suite: 88 passed before implementation.
- New module suite: 18 passed at the first integrated checkpoint, including six PDF formats, challan conversion, credit caps, purchase returns/refunds, named accounts, opening settlements, concurrent receipts and a 4000-party import.
- A proposal PDF wording regression was identified by the full suite and fixed without changing its test. Targeted regression: 1 passed.
- Expanded full-suite checkpoint: 129 passed. Final affected suites: 49 passed. Last unit/safety checks: 12 passed. Exact sequencing and limitations are recorded in VERIFICATION.md.
- Browser QA is isolated from live data and covers purchase entry, saved totals, supplier ledger, accounts and report navigation. No physical printer/mobile device or live external integration has been exercised.

## Approved local activation — 18 October 2026

The user explicitly approved the additive Atlas setup and restart of the local company/admin apps. The services were stopped before backup. Private backup atlas-20261018-143358.json was restore-verified: 38 collection exports, 574 documents, SHA-256 c18cf572b1634dd1e2f0c12a0ab38340ca8fe111800df5125e42fea181e29567. The guarded preparation script succeeded. Every original document and every original counter compared equal afterward; only the new storage, indexes and counters were added.

Local company port 5000 and admin port 5001 were restarted. Home and both login endpoints returned HTTP 200; the company served the new purchase assets. The main browser is at the company login; authenticated production workflow posting was not performed. Sign in with existing credentials to see the permitted new modules. The sample preview on 5002 remains separate and disposable. Render has not been updated; coordinate its deployment before using new financial workflows through different code versions against the same database.
