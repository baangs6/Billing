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


## Collapsible sidebar

The company sidebar now keeps Dashboard directly accessible and groups all existing permission-filtered links under Sales, Purchases, Catalog, Money and Administration. Native details/summary controls support keyboard expansion. Empty groups are omitted; the current section opens automatically, including the existing Finance and Reports aliases. No routes, permissions or business records are changed.

Verification: two isolated template tests passed, checking all 18 links occur exactly once, only the current group opens, and a subscription-only user receives no empty or unauthorized groups. Browser checks confirmed expanding Money and opening Finance keeps that group expanded. Company and preserved sample services were restarted and their login pages returned HTTP 200. Screenshot capture was blocked by an in-app browser policy error associated with the stale preview tab; visual screenshot verification and the full suite were not completed. No push or deployment performed.


## Phone layout

At 768px and below, Workspace menu toggles the company sidebar with aria-expanded/aria-controls. Escape closes the menu and returns focus to its button. Crossing the breakpoint restores desktop navigation or collapses phone navigation. With JavaScript unavailable the full navigation remains accessible. Forms and filters stack, header controls wrap, touch controls are enlarged, dialogs fit the viewport, and wide tables scroll inside their panels. No routes, data, permissions or PDF layouts changed.

Validation: both sidebar template tests and the Node navigation behavior check passed (initial phone/desktop state, button toggle, Escape/focus, breakpoint changes, pages without a sidebar). Desktop browser appearance checked. Full suite and physical phone/iOS checks not performed; exact phone viewport visual QA remains outstanding. Local company and preserved sample services refreshed. No GitHub push or Render deployment.
