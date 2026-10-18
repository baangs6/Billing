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

The full feature request remains partial. FEATURE_PROGRESS.md lists individual gaps; missing credentials do not make unfinished internal work complete. A sample-data preview is running on localhost port 5002 at the user request to see changes; its database is disposable. The user application on port 5000 is unchanged. New schemas have not been applied to the configured business database, the running user services have not been restarted onto this branch, and nothing has been pushed or deployed. Activation requires the user approval specified by the master prompt.
