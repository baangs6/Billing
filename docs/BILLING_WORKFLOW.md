# Invoice creation follow-up

Billing retains the existing customer/product popups, unit conversion, GST/non-GST, common discount, charges, stock posting, payments and document conversions.

## Added workflows

- Walk-in sale: no customer profile, full payment required. Anonymous snapshots use reserved customer ID 0; real customer IDs start at 1. Select the place-of-supply state for interstate GST sales. Returns/refunds stay linked to the original invoice, and aggregate walk-in balances appear in customer balance reports.
- Customer information: billing/shipping address, state, PIN, phone, GSTIN, PAN, credit days and current previous balance. Balances include openings, payments, credits and refunds, exclude cancelled/trashed bills and exclude the invoice being edited. Opening balance settlements retain their existing sign convention.
- Due date: defaults from invoice date plus customer credit days; may be overridden, but cannot precede the invoice date. The e-way bill field records an existing 12-digit number; it does not generate or validate an e-way bill with a government service.
- Manual round-off: signed adjustment from INR -1.00 through 1.00, at most two decimal places. Cannot combine a nonzero manual adjustment with automatic rounding or make a total negative. Taxes and item amounts remain unchanged.
- Bank popup: finance-manage users can create a zero-opening bank ledger without leaving billing. The new bank is selected for printing, while the payment ledger stays independently selectable. CSRF, tenant ownership, role checks, transactional writes and duplicate-submission protection apply.
- Printing: save bank-only, UPI-only or combined details plus time/QR/previous-balance preferences on each invoice. QR is generated only when a positive balance remains. Selected bank/UPI details are snapshotted, not read afresh during download. Editing with no bank replacement preserves the saved bank/UPI details.
- Thermal PDFs: Compact, Simple, Classic and Advanced styles for both supported widths. Duplicate PDF output adds DUPLICATE COPY without creating a second invoice or modifying records. Paper size remains configurable in Business profile & printing.

No database migration, new dependency, provider account, financial backfill, credential change or production posting is required. Existing documents retain their data; newly introduced optional fields are absent on legacy invoices.

## Remaining work

Batch/expiry/serial/IMEI stock allocation, arbitrary custom header fields, pre-save PDF preview, OCR plus human review, TDS/TCS rules, authorized GST lookup/e-way generation, messaging providers and scheduled accountant delivery are not implemented here. Per-line billing discounts remain absent as the user previously requested. Physical printer and real payment-app testing remain outstanding.


## Verification result

The selected billing/PDF/extended/finance/application regression run passed 87 tests in 604.05 seconds. After the final adjustments, all seven targeted billing-option/workflow tests passed in 61.72 seconds, including anonymous returns, cross-tenant bank rejection, immutable bank snapshots, role restrictions, rollback and interstate tax. Eight thermal width/layout combinations were checked in the broader run; synthetic A4 and 58mm advanced PDFs were rendered and visually inspected. The isolated browser test saved a fully paid walk-in invoice and verified bank-popup selection and customer outstanding information. Final preview browser checks confirmed the place-of-supply field appears only in walk-in mode.

Both local services were refreshed. Fingerprints across 24 business/subscription collections per database matched before and after for the real company database and the preserved sample preview. Login endpoints returned HTTP 200. No production financial records were posted for testing. No migration, GitHub push or Render deployment was performed. The full repository suite and physical printer/device behavior were not rechecked.
