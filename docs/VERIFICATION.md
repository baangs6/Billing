# Verification and remaining activation gate

All integration tests use disposable `ledger_test_*` databases, separate from the configured business database. No production financial records are created, edited or deleted for verification. An inherited global WSGI app import also runs finance-storage metadata setup. Earlier runs reached that idempotent initializer on the configured database; they did not create or modify production financial records. The new tests/conftest.py redirects even import-time setup into a disposable bootstrap database before app imports, with a regression assertion and session cleanup. A failed-setup cleanup regression ensures temporary databases are dropped even if initialization fails. Run one Atlas-dependent suite at a time: concurrent full suites exceeded the cluster collection quota during development; two confirmed-empty failed-setup test databases were removed, and unknown nonempty databases were preserved.

## Automated verification

- Original baseline: **88 passed**.
- Integrated core checkpoint: **117 passed**, 1022.65 seconds, before the unit/service/photo slice.
- Reset/PDF/precision fixes: **18 passed** in the targeted suite before unit wiring.
- Unit, trade and extended feature checkpoint: **39 passed, 1 failed**. The failure proved JPEG comments survived a PIL conversion. Pixel copying into a fresh image fixed the cause; the unchanged metadata test then passed.
- Latest pure unit/browser-rate/photo/QR checks: **7 passed**, including exponent-zero resource bounds.
- Expanded full-suite checkpoint: **129 passed**, 1014.33 seconds. This preceded the last Decimal export/QR formatting and test-bootstrap isolation changes. Their affected suites were rerun separately below.
- Final affected suites (units, safety harness, trade, extended features, Finance): **49 passed**, 354.59 seconds, including large-paisa ledgers, management exports, invoice/purchase PDFs and bootstrap isolation.
- Last unit/resource-bound and injected-cleanup-error checks: **12 passed**, 4.46 seconds.
- Python compilation, JavaScript syntax and `git diff --check`: passed before final runtime checks.
- No skipped/deleted tests or relaxed assertions were used to obtain passing results.

## UI and PDFs

Isolated QA includes purchase/order entry and posting, supplier ledger, named account balances/transfers, reporting navigation, and product unit/price controls. Test data is synthetic. Saved screenshots/PDF renders are under ignored `tmp/review/`, not committed customer artifacts.

Rendered A4 Advanced, 58 mm and 80 mm invoices were visually checked. Both thermal examples fit one content-sized page (421 points high). A4 was one page. The QR uses a fake test UPI address; no payment was attempted. Return-note extraction verifies pre-round credit + round-off = displayed total for a partial paise-level GST return.

## Not checked / not available

Physical printers, actual mobile devices, native app builds, real payment-app scanning, live SMTP/WhatsApp/SMS delivery, independent penetration testing and dependency vulnerability scanning are not verified. No new dependency was added; `pip_audit` was unavailable. Google Fonts is blocked by the existing CSP; the policy was not weakened.

The full feature request remains partial. FEATURE_PROGRESS.md lists individual gaps; missing credentials do not make unfinished internal work complete. A sample-data preview is running on localhost port 5002 at the user request to see changes; its database is disposable. The user application on port 5000 is unchanged. After explicit user approval, the additive Atlas setup and local service restart completed. The fresh 574-document backup passed restore verification, and all existing documents/counters compared equal after setup. Both local login endpoints and the home page returned HTTP 200; new assets are served on 5000. The main browser requires the user to sign in. No production financial workflow was posted for testing. GitHub push and Render deployment have not occurred. See IMPLEMENTATION_REVIEW.md for activation details.


## Invoice workflow follow-up (2026-10-19)

Selected regression run: `python -m pytest tests/test_billing_options.py tests/test_thermal_layouts.py tests/test_billing_workflow.py tests/test_extended.py tests/test_finance.py tests/test_app.py -q --tb=short` passed 87 tests in 604.05 seconds before final small place-of-supply/access/balance-query adjustments. A subsequent targeted run checks the final version; see BILLING_WORKFLOW.md for its result.

An isolated port-5003 browser workspace verified customer outstanding information, fully paid walk-in entry, manual rounding (100.49 minus 0.49 = 100.00), printing options, quick bank creation and successful invoice saving/payment history. The temporary QA database was cleaned. Company and preserved preview records were not used for test postings. Synthetic A4 and 58mm advanced duplicate PDFs were rendered and visually inspected; all eight width/layout combinations have text/bounds checks. No physical printer, external tax lookup, payment app, WhatsApp/SMS/email service or OCR workflow was tested. JavaScript syntax, Python compilation and diff whitespace checks passed.

Final follow-up: all seven targeted billing tests passed in 61.72 seconds. Both company/preview login endpoints returned HTTP 200 after refresh, and all 24 checked collections in each database retained their record fingerprints. The final billing screen was verified in the preserved preview without posting a new sample invoice there.


## Business settings follow-up (2026-10-19)

Final targeted run passed 24 tests in 281.01 seconds: business settings/lifecycle, company reset isolation, password recovery, purchase/sales returns and billing workflow. A separate final pure PDF run passed all 14 thermal/identity tests. The preceding extended/printing run had 34 passing cases; two new regression fixtures failed on duplicate synthetic emails before exercising product code, were corrected and passed in the final run. Earlier duplicate-form fixture failure was corrected to preserve MultiDict values; the final classification test passes.

Two fresh-context focused reviewers found shared identity preservation and future-opening carry-forward defects. Both were fixed and re-reviewed without further findings. User declined optional cross-model review. Tests verify independent company records/approval, root credential session revocation, preservation of another root's staff membership during deletion/reset, staff denial, historical financial locks, future payments, service completion, immutable old snapshots, and custom headers on purchase/order/note exports.

Isolated browser QA on port 5003 verified multi-select saving, dynamic custom header addition, Account, Your businesses, financial-year and deletion confirmation forms; its temporary database was cleaned. No real destructive workflow was submitted. Synthetic logo/signature/header PDFs rendered in all six formats; A5 and 58mm were visually inspected. JavaScript syntax, Python compilation and diff whitespace checks passed. Physical printer calibration remains unverified.

Local company and preserved preview services were refreshed. Both login endpoints returned HTTP 200, the new profile screen loaded in the preserved preview, and fingerprints of all 24 checked operational collections in each database remained equal before/after refresh. No database migration or historical backfill was required. No GitHub push or Render deployment occurred.


## Supplied billing design follow-up (2026-10-19)

Adapted the desktop/mobile references from stitch_modern_responsive_mobile_redesign.zip into the existing billing form. Page-scoped static/billing.css provides the split desktop workflow/summary, blue input surfaces, compact table and mobile item cards/save bar. Existing form names, IDs, permission checks, quick-add dialogs, calculations and server endpoints remain intact. The reference's unimplemented draft/outbound/QR-upload placeholder actions were not added as fake controls.

Seven billing workflow/options regression tests passed in 56.20 seconds. Isolated browser checks at 1280px and 390px verified desktop table width fits its container, no page-wide horizontal overflow, editable mobile fields and a fixed mobile save total. Changing sample quantity from 2 to 3 updated the total to INR 354 and saved successfully with the existing INR 50 payment preserved. The temporary QA database was cleaned. Browser viewport override was reset. JavaScript syntax and diff whitespace checks passed.

Company port 5000 was refreshed and the preserved preview on 5002 started without reseeding. All 24 checked operational collections in both databases retained equal fingerprints. Company login, new billing CSS and owner login returned HTTP 200. The sample preview is open on the updated editor. No physical mobile device or browser-engine matrix was tested; no GitHub push or Render deployment occurred.


Invoice optional totals (2026-10-19): HTML and all six sales PDF formats hide zero/missing credit notes, refunded and round-off rows; nonzero values including negative rounding remain visible. Billing preview also omits a zero round-off total. Selected HTML/PDF tests passed 27 cases in 23.80 seconds. No calculations or stored financial records changed.


## Complete mobile layout follow-up (2026-10-19)

Shared company/owner responsive styles, owner mobile navigation and table-scrolling guidance added. See MOBILE_LAYOUTS.md for the page inventory and measured phone/tablet audits. Two navigation/table tests and three page/export/auth/printing tests passed. No financial records were posted or reset for this layout change; all visual data was disposable. No GitHub push or Render deployment is included.

Final activation: company, owner and preserved-preview login endpoints returned HTTP 200 and serve the shared responsive stylesheet. All 24 checked operational collections in each company/preview database retained equal fingerprints across service refresh. QA databases were cleaned; temporary browser tabs/viewport overrides were removed.


Invoice rate column (2026-10-25): added saved per-unit RATE beside MRP in A5 and all A4 sales invoice PDFs, including GST/non-GST documents. Charge rows retain dashes for quantity/rate/MRP. HTML print already had Rate; thermal receipts retain quantity x rate. All 34 PDF tests passed; rendered A5 GST layout visually checked. No stored invoice values changed.


Pre-discount invoice item amounts (2026-10-25): HTML print and A4/A5/thermal PDFs display saved quantity times unit rate before discount; invoice discount/tax/final totals remain unchanged. Exact decimal-rate rounding is shared. Regression cases cover INR 9000 line / INR 300 discount / INR 8700 total and fractional rates. No stored data rewritten.


MRP presentation (2026-10-25): removed separate Rate column from invoice HTML and A4/A5 PDFs. MRP displays bracketed percentage based solely on saved MRP minus selling rate, excluding common discount. Thermal also shows MRP/percentage. Amount remains selling rate times quantity, with common discount only in totals. Missing/zero MRP avoids division by zero; exact unit rates supported. All 41 selected PDF/helper/HTML tests passed in 24.14 seconds; A5 example visually verified. No data rewrite.


Manual service reminders (2026-10-25): invoice-edit users can add customer/due-date/notes reminders independently of invoices. Existing invoice annual reminders remain. Both sources feed due/upcoming/completed views and dashboard counts. Manual records are tenant-scoped in business settings, capped at 1000 to bound document size; full company reset removes them. Submission tokens prevent duplicate creation. Two isolated tests passed in 27.70 seconds covering creation, replay, dashboard count, completion, missing customer, invalid date and role denial. No live reminder or invoice created during testing.


Reminder customer lookup (2026-10-25): searchable name/phone/email selection and permission-controlled customer popup reuse the billing lookup script and extracted shared popup template. Missing customers save/select without leaving the reminder form; hidden customer ID remains server validated. Existing billing/manual reminder tests passed (3), plus a dedicated quick-add-to-reminder integration test. Disposable browser QA verified filtering, missing-name popup prefill and saving/selecting a synthetic customer; QA database cleaned. No live customer was created.


Clean default invoice (2026-10-25): supplied browser-print reference was inspected and rendered (two pages with browser date/title/URL/footer). Added ledger_invoice_pdf.py to reproduce its blue-accent A4 visual structure without browser chrome, page footer or watermark. Download/Preview/Print default to clean one-page A4 even for existing invoice snapshots; original configured layout remains via Saved print format. No stored snapshots changed. Spacing/font compacts to 7pt, then KeepInFrame scales overflow onto one page without discarding rows; very long invoices necessarily have smaller text. Company profile exposes A4 clean invoice as the new default choice. Print opens the generated PDF viewer, from which users print; browser HTML Ctrl+P remains browser controlled. Tests: 46 pure PDF checks passed, then final six clean-layout cases passed after grand-total color refinement. Two route/print regression tests passed in 44.99 seconds. GST/non-GST 1/12/60 item one-page checks verify every row, bounds, totals and no header/footer/zero optional rows. Final A4 PNG visually checked. No physical printer tested.


3-inch thermal shortcut (2026-10-25): invoice toolbar provides Print and Download 3-inch thermal actions using existing 80mm renderer. Default clean A4 stays available. Route regression passed in 32.78 seconds for inline/download headers, 227pt paper width, item contents and unchanged invoice snapshots. Physical printer calibration was not tested.
