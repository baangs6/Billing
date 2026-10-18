# Navigation consolidation

The overlapping interfaces are consolidated without merging, copying, deleting or rewriting business records. No database migration is required.

## Finance

One sidebar entry opens Finance. Its two views retain the existing routes:

- /finance: income/expenses, categories, attachments, account/date filters, transaction edits/voids and exports.
- /accounts: named cash/bank accounts, bank/UPI details, opening balances, source-derived ledgers, as-of balances and internal transfers.

Both views highlight Finance in the sidebar. Invoice payment entry and purchase settlement workflows remain available in their original modules; bank ledgers derive movements from those records rather than creating duplicate receipts.

## Reports and stock

One shared report selector is used on /reports and /accounting-reports. The former dispatches accounting report selections to the existing permission-checked accounting route, preserving dates and export choices. Legacy bookmarked URLs remain valid. CSV/PDF exports remain on legacy reports; CSV/Excel/PDF remain on accounting reports. Export controls respect existing permissions and PDF plan access.

All 19 report types are retained. Outstanding invoices and Customer balances (including opening) remain distinct because their scopes differ. Stock quantities and Stock valuation (catalog cost) remain distinct because one measures quantities and the other values stock. Inventory has a direct stock valuation link, retaining its adjustments and movement history.

Suppliers shortcuts open the same supplier records; they do not create a second supplier module. Products and Inventory, and Billing and Invoices, remain distinct workflows. No calculation, posting, payment, stock reversal, permission enforcement or reset routine was replaced.

## Verification

The integration regression checks canonical and legacy routes, all eight accounting report selections, CSV/Excel/PDF exports, a single Finance sidebar entry, both Finance views, role restrictions and equality of financial/stock records before and after navigation. Existing extended and Finance regression suites are run together. Browser checks use an isolated disposable database; actual business records are not posted for testing.

Results: 24 extended/Finance tests passed in 214.04 seconds. Browser checks confirmed switching Finance views and choosing Purchases from the shared report selector with CSV/Excel/PDF retained. The company app on port 5000 was restarted; fingerprints of all 23 checked business/financial collections matched before and after. The existing sample preview on 5002 was refreshed against the same sample database, and every original preview record matched its fingerprint afterward. No schema migration or financial posting was performed. Main/admin login endpoints returned HTTP 200. The sample Finance view was also checked at narrow panel width. GitHub push and Render deployment were not performed.
