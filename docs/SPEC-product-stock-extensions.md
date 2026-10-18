# Product and stock extensions

Status: unit/service/pricing slice implemented in development; regression and adversarial review in progress. Per-item discount configuration and lot/serial tracking remain unimplemented.

## Preserve the base model

Existing inventory.quantity remains the canonical balance in thousandths of the primary unit. Existing products default to ordinary stock, retail/exclusive prices, primary units and no lot tracking. No existing stock, invoice IDs, prices or saved snapshots are rewritten automatically.

## Product options

Add a product Options page, linked from Products rather than a duplicate sidebar module. Store optional wholesale price, default item-discount percentage, inclusive/exclusive pricing, service classification and alternate unit/factor under product data. Preserve unknown existing data when editing basic product fields. Photos are bounded re-encoded thumbnails under product data, served by an authenticated tenant route with no-store. Product-row projections exclude image blobs. No new media collection or public filesystem URL is needed for this single-thumbnail workflow.

## Units and money contract

- quantity remains the displayed document quantity in thousandths of its selected unit.
- stock_quantity is the primary-unit quantity in thousandths, snapshotted at posting; old lines fall back to quantity.
- Alternate factor means primary units per alternate unit. Multiplication must yield an exact integer primary thousandth. Reject unrepresentable quantities instead of rounding physical stock.
- rate is the entered per-selected-unit rate in paise. Inclusive entries retain their original gross rate; base_amount and included_tax carry the exact internal breakdown.
- Money and stock conversions run server-side. Retail/wholesale defaults may be selected in the UI, while explicit authorized selling-price overrides remain possible.
- line_discount is distinct from allocated invoice common discount. Keep the current common-discount-only default; optional per-item controls must not double-apply historical allocations.
- Invoice edits reverse old snapshotted stock_quantity, then post the new one. Returns prorate the original stock_quantity and tax components. Challan conversion compares canonical dispatched quantities.
- Purchase orders preserve ordered-unit conversion for receipts even if future product defaults change. Batch receipt limits use source-line references.

## Batch / serial contract

Track lot balances alongside the canonical inventory balance. Every posting must preserve the sum of available/quarantined lot quantities equal to canonical stock for tracked products. Batch metadata includes batch number, manufacture and expiry dates. Serial/IMEI records represent individual primary units and cannot be sold twice. Expired-batch sales must be clearly controlled.

Enabling tracking on existing stock cannot invent batch or serial identifiers. Existing quantities require an explicit allocation/reconciliation workflow. Historical records retain their original absent tracking metadata; legacy reversals need a clearly identified unallocated/quarantined path, not fabricated serial numbers. New sales consume only explicitly allocated valid lots/serials. Actual source identifiers must be entered by the company.

## Required call sites

Products/basic import, product options, product picker data, invoice/proposal form rendering, line-item validation, calculate, move, opening stock, inventory adjustments, purchase receipts/order conversion, challan dispatch/cancellation, invoice edits/cancellation/Trash, sales/purchase returns, stock reports, image serving, company/owner reset dependencies, backup collection inventory and additive schema preparation.

## Acceptance tests

Primary/alternate arithmetic and fractional rejection; inclusive gross preservation; default/wholesale prices; simultaneous line/common discounts; service lines do not move physical stock; edit/cancel/return reversals use original conversions; changed product defaults cannot change historical returns; partial order receipts; batch expiry selection; serial uniqueness and return recovery; concurrent stock consumption; duplicate submissions; tenant/media isolation; archived/plan-restricted access; linked resets and legacy invoice compatibility. Browser QA uses isolated data and PDFs are rendered before review.
