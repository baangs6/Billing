# Integrated feature progress

Source: user master checklist, 18 October 2026. Status means verified behavior, not planned marketing claims. The linked reference video could not be retrieved (YouTube throttling); no video-only behavior is assumed.

Baseline: c2333e7. Working branch: codex/complete-billing-features. Production writes, GitHub push and deployment are not authorized.

| Requirement | Status | Evidence / remaining work |
|---|---|---|
| Company name, logo, mobile, email, address, city, state and PIN code. | Implemented in development | Existing settings plus city in Additional profile. |
| GST registration toggle and GSTIN. | Implemented in development | Business profile registration choice; GSTIN structural validation. Historical snapshots unchanged. |
| PAN details. | Implemented in development | Additional business profile and party fields. |
| TDS and TCS configuration where legally applicable. | Blocked / not applicable | Needs business-specific applicability, rates, thresholds and CA-approved posting rules. Not implemented. |
| Authorized signature image and optional empty signature box. | Implemented in development | Existing signature upload plus optional empty PDF signature box. |
| Custom invoice header fields for MSME, drug licence, website and additional business information. | Implemented in development | Additional profile fields rendered on new A4/A5 invoice snapshots. |
| Business type: Retail, Wholesale, Distributor, Manufacturing and Service. | Implemented in development | Additional business profile classification. |
| Industry classification and business registration type. | Implemented in development | Additional business profile fields. |
| Multiple businesses under one account, subject to SaaS plan restrictions. | Blocked / not applicable | Existing globally unique user email/account model needs a separately reviewed identity/index migration before activation. Not implemented. |
| Financial-year closing with safe balance carry-forward. | Blocked / not applicable | Needs agreed accounting/carry-forward policy and approved migration; no close is posted. |
| Company data export and backup. | Partial | Private full-database snapshot and restore verification implemented. No tenant self-service full backup/restore UI. |
| Safe business deletion and reset controls. | Partial | Existing password-protected resets preserved; linked new sections added. Owner archival retained; no new account deletion workflow. |
| Account details, plan status, renewal history and subscription tax invoices. | Partial | Existing account/plan/renewal/payment history retained; no subscription GST tax-invoice generator. |
| Multiple professional A4 GST invoice themes. | Partial | Three A4 visual variants of the existing grid; no independent visual template designer. |
| Non-GST billbook theme. | Existing / preserved | sales_invoice_pdf.py; original Non-GST format retained. |
| A5 compact invoice. | Existing / preserved | Original A5 landscape renderer retained. |
| 2-inch and 3-inch thermal printing. | Implemented in development | 58/80mm PDF formats; physical printer behavior not tested. |
| Compact, Simple, Classic and Advanced thermal layouts. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Live invoice preview. | Partial | Existing live totals and saved PDF preview. No pre-posting PDF preview. |
| Show/hide GST columns, item description, previous balance and invoice time. | Partial | GST column, description and creation-time preferences implemented. Previous-party-balance printing not implemented. |
| Configurable invoice-level fields such as PO number and vehicle number. | Implemented in development | Billing fields, immutable snapshot, invoice HTML and A4/A5 PDF. |
| Customizable invoice columns. | Partial | GST-column visibility only; arbitrary column configuration not implemented. |
| Custom terms, bank details, signature and logo placement. | Partial | Existing terms/logo/signature retained and payment visibility added. Arbitrary placement not implemented. |
| UPI QR code on invoices. | Implemented in development | ReportLab QR from configured UPI ID, business name and outstanding amount. Does not confirm payment. |
| Bank-only, UPI-only or combined payment details. | Implemented in development | Snapshot print preference. |
| Print, PDF download and WhatsApp/SMS sharing. | Partial | Print/download and existing native file sharing retained. Provider-driven WhatsApp/SMS not configured or implemented. |
| Maintain accurate invoice formatting across multiple pages. | Partial | Existing A4/A5 repeated tables retained; thermal PDFs paginate. Printer margins and every long-note/theme combination remain untested. |
| Separate Customer and Supplier records. | Implemented in development | Separate tenant-scoped suppliers collection and UI. |
| Create, edit, archive, search and filter parties. | Implemented in development | Existing Customers plus supplier create/edit/archive/search/include-archived. |
| GSTIN validation and optional authorized GST details lookup. | Partial | Structure only. Registration status, checksum and authorized lookup are not verified. |
| PAN details and contact person. | Implemented in development | Party fields; PAN structure checked for customer/business. Supplier PAN is recorded only. |
| Billing and shipping addresses. | Implemented in development | Customer and supplier fields; historical invoice customer snapshots remain intact. |
| Party categories and custom fields. | Partial | Category and additional fixed fields. User-defined field schemas not implemented. |
| Opening balances: To Collect / To Pay. | Implemented in development | Signed opening balances and bounded, idempotent opening settlements. |
| Credit periods and credit limits. | Implemented in development | Customer due dates and credit cap; supplier credit cap and stored credit period. |
| Customer and supplier bank details. | Implemented in development | Party bank/IFSC/UPI text fields. |
| Detailed party ledgers and outstanding balances. | Implemented in development | Customer/supplier opening balances, invoices, receipts/payments, returns and refunds. |
| Bulk imports from Excel/CSV, targeting up to 4,000 records per supported import with validated batching and error reporting. | Implemented in development | Prevalidation of all rows; batches of 200 in one transaction, 5 MB limit, duplicate-submission protection. |
| Export and downloadable statements. | Implemented in development | Party CSV/PDF statements; accounting CSV/XLSX/PDF exports. |
| Preserve existing customer history and invoice relationships. | Existing / preserved | Existing IDs, invoice snapshots and tenant references are retained; no backfill. |
| Products and services. | Implemented in development | Catalog classification distinguishes physical stock and nonstock services; history locks classification changes. |
| Product categories and descriptions. | Existing / preserved | Existing products/categories and product import. |
| SKU/item codes, HSN/SAC and GST rates. | Existing / preserved | Existing product fields; optional generated SKU behavior retained. |
| Selling, purchase, MRP and wholesale prices. | Implemented in development | Optional wholesale price and billing selector; existing prices preserved. |
| Tax-inclusive and tax-exclusive pricing. | Implemented in development | Product default and invoice/proposal line pricing; purchase document pricing. Inclusive gross preserved before optional discounts. |
| Product-level default discounts. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Product images. | Implemented in development | Bounded JPEG/PNG upload, re-encoded private thumbnail, tenant-authenticated image endpoint; blobs excluded from pickers. |
| Primary and alternate units with conversion rates. | Implemented in development | Product conversion factor, selected document unit, saved canonical stock quantity; import supports optional fields. |
| Automatic unit-based pricing and stock conversions. | Implemented in development | Exact default rate conversion; primary thousandths required; edits, returns, dispatch and receipts use saved conversions. |
| Opening stock and stock adjustment history. | Existing / preserved | Existing inventory/stock_movements and serialized writes. |
| Low-stock thresholds. | Existing / preserved | Existing product thresholds and dashboard indicators. |
| Product import using Excel/CSV, with larger validated imports where technically safe. | Existing / preserved | Existing bounded 500-product import retained. Party imports have a separate 4000-record limit. |
| Batch numbers, manufacturing dates and expiry dates. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Serial number and IMEI tracking. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Batch/serial selection during purchases and sales. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Stock valuation reporting with clearly defined methods. | Implemented in development | Current catalog purchase cost times current stock. Not FIFO or weighted average. |
| Stock movement audit trails. | Existing / preserved | Existing stock_movements, extended with purchase/return/challan reasons. |
| Inventory reconciliation and stock corrections. | Existing / preserved | Existing settings confirmation and stock adjustment controls retained. |
| Product library capability if suitable product data is available. | Blocked / not applicable | No licensed product library/source data supplied. |
| Optional online-store product visibility settings if an online-store integration exists. | Blocked / not applicable | Not applicable: no online-store integration exists. |
| Supplier purchase invoices. | Implemented in development | Immutable posted supplier purchases with snapshots. |
| Original supplier invoice number. | Implemented in development | Stored and duplicate-checked per supplier for final purchases. |
| Multiple purchase items and quantities. | Implemented in development | Catalog and manual items; up to 200 lines. |
| GST-inclusive/exclusive purchase calculations. | Implemented in development | Paise calculations preserve inclusive gross amounts; common discount applies before GST. |
| Discounts, additional charges, TCS and round-off where applicable. | Partial | Purchase common discount and rounding implemented. Named purchase charge treatment/TCS configuration not implemented. |
| Paid, partially paid and unpaid purchase statuses. | Implemented in development | Balances derive from linked payments and returns/refunds. |
| Automatic stock inward on finalization. | Implemented in development | Purchase posting and stock receipt occur in the same tenant transaction. |
| Supplier outstanding balances. | Implemented in development | Supplier ledger and payables export. |
| Purchase order creation. | Implemented in development | Separate nonposting purchase_orders records. |
| Purchase order PDF and printing. | Implemented in development | PDF download; no browser-specific print integration required. |
| Convert purchase orders into purchase invoices. | Implemented in development | Source order line references and received-quantity controls. |
| Partial purchase order receipts. | Implemented in development | Remaining source quantities, atomic receipt limits and RECEIVED status. |
| Purchase returns with full or partial quantities. | Implemented in development | Returns cap quantities to unreturned original purchase lines. |
| Automatic stock reduction on valid returns. | Implemented in development | Linked stock movement in the return transaction. |
| Debit notes linked to purchases. | Implemented in development | Purchase return records with original quantities/tax and printable debit notes. |
| Supplier refunds and credits. | Implemented in development | Bounded refunds against resulting supplier credit. |
| Payment Out with cash, UPI, bank and partial settlement. | Implemented in development | Source-linked supplier payments and optional named account. |
| Supplier payment history. | Implemented in development | Purchase detail, supplier ledger and cash/bank source ledger. |
| Supplier purchase reports. | Implemented in development | Purchases and payables management reports. |
| Optional purchase invoice image scanning/OCR with explicit human verification before posting financial records. | Blocked / not applicable | Not implemented; OCR engine/provider and human review workflow still required. |
| GST and non-GST invoices. | Existing / preserved | Existing invoice workflows retained. |
| Walk-in/cash customers. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Primary and alternate unit billing. | Implemented in development | Invoice/proposal/purchase selectors; historical conversion preserved. |
| Product and service line items. | Existing / preserved | Existing catalog products and manual service lines retained. |
| Wholesale price selection. | Implemented in development | Retail/wholesale selector for configured product prices. |
| Item discounts and invoice discounts. | Partial | Existing legacy/proposal line discounts preserved; billing common discount retained as explicitly requested earlier. No new per-item discount UI. |
| Additional charges and round-off. | Existing / preserved | Existing summary charges, common discount and optional rupee rounding retained. |
| Multiple payment methods. | Existing / preserved | Cash, UPI, Bank Transfer, Card, Cheque and Other retained. |
| Partial and full payments. | Existing / preserved | Existing customer payment and payment editing workflows retained; refunded invoices protected. |
| Invoice outstanding tracking. | Existing / preserved | Existing invoice balances extended with credit notes and refunds. |
| Quotation/estimate creation and conversion. | Existing / preserved | Existing proposals and conversion retained. |
| Proforma invoices and conversion. | Implemented in development | Document kind on existing proposals; immutable conversion link. |
| Delivery challans and conversion into sales invoices. | Implemented in development | Draft/dispatch/cancel dispatch; conversion verifies stock quantities and prevents a second stock reduction. |
| Sales returns linked to original invoices. | Implemented in development | Tenant-scoped quantity-limited returns using original amounts/tax. |
| Credit notes for returns, discounts and value adjustments. | Partial | Quantity-linked return credit notes implemented. Standalone value-only adjustments not implemented. |
| Customer refunds and credit balances. | Implemented in development | Refund caps, source ledger postings and protected historical documents. |
| Correct stock reversal and financial adjustments. | Implemented in development | Returns, dispatch cancellation and invoice conversion tested; partial tax allocation uses cumulative paise arithmetic. |
| Editable and printable documents. | Partial | Existing invoice/proposal edits preserved; posted purchases/returns are immutable. Purchase correction/edit workflow not implemented. |
| WhatsApp/SMS invoice sharing through configured providers. | Blocked / not applicable | No provider credentials/sender approval/consent setup. No messages sent. |
| Multiple named bank accounts. | Implemented in development | Named account openings; existing unassigned records remain in legacy Cash/Bank/Other accounts. |
| Bank account details, IFSC, UPI and opening balance. | Implemented in development | Account creation stores details and opening date/balance; metadata editing is not provided yet. |
| Cash-in-hand ledger. | Implemented in development | Derived ledger of recorded cash movements. |
| Bank-wise transaction ledger. | Implemented in development | Account selection on receipts, purchases, refunds and expenses. |
| Cash-to-bank transfers. | Implemented in development | Balanced transfers with duplicate-request protection. |
| Bank-to-cash withdrawals. | Implemented in development | Same balanced transfer workflow. |
| Bank-to-bank transfers. | Implemented in development | Same balanced transfer workflow; source overdraw protection includes later recorded dates. |
| Financial transaction references and remarks. | Existing / preserved | Existing payments/finance plus new supplier, refund and transfer references. |
| Automatic postings from sales, purchases, payments and expenses. | Implemented in development | Read-through source ledger avoids duplicating cash postings. Unpaid documents do not move cash. |
| Expense categories. | Existing / preserved | Existing finance categories retained. |
| GST and non-GST expenses. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Expense items, HSN and GST rates. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Input Tax Credit eligibility classification. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Original expense bill numbers. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Receipt attachments. | Existing / preserved | Existing tenant-scoped PDF/PNG/JPEG receipt upload/download retained. |
| Supplier-linked expenses. | Not implemented | Remains in the consolidated backlog; no production behavior is claimed. |
| Expense and cash-flow reports. | Existing / preserved | Existing finance totals and CSV/PDF retained; supplier settlements and refunds included. |
| Reconciliation controls and complete audit trails. | Partial | Existing stock reconciliation and audit trail extended. No bank-statement reconciliation or period lock. |
| GST sales reports. | Implemented in development | Existing sales filter plus return-adjusted management GST summary. |
| GST purchase reports. | Implemented in development | Purchase report and return-adjusted management GST summary. |
| HSN/SAC summaries. | Implemented in development | Sales HSN summary including dated credit notes. |
| CGST, SGST and IGST breakdowns. | Implemented in development | Source documents and return-adjusted management summary. |
| Credit/debit note reporting. | Implemented in development | Management reports and individual printable linked notes. |
| Customer and supplier ledgers. | Implemented in development | As described under party management. |
| Receivables and payables reports. | Implemented in development | As-of end-date balances, including opening settlements and refunds. |
| Inventory and stock valuation reports. | Implemented in development | Existing inventory plus explicitly named catalog-cost valuation. |
| Purchase and sales summaries. | Implemented in development | Existing sales reports retained; purchase and GST summaries added. |
| Daily, monthly and yearly reports. | Partial | Existing daily/monthly sales and selectable date ranges; no new year-end close or consolidated statutory reporting. |
| CA report export in Excel/CSV/PDF. | Implemented in development | Manual management exports in all three formats; no automatic delivery. |
| GSTR-1 and relevant GSTR-2B reconciliation support, with accurate reporting definitions. | Blocked / not applicable | Not implemented. Management summaries are not filing-ready GSTR returns or purchase ITC reconciliation. |
| Scheduled monthly CA report delivery by email or approved WhatsApp integrations. | Blocked / not applicable | No email/WhatsApp provider or scheduler configured. Not implemented. |
| Configurable accountant contact information. | Implemented in development | Additional profile email/phone only; no message is sent. |
| Invoice sharing after creation. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Customer payment due reminders. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Overdue collection alerts. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Supplier payment reminders. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Low-stock notifications. | Partial | Existing dashboard/stock indicators only. Outbound notifications absent. |
| Daily sales summaries. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Outstanding payment summaries. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Service and AMC reminders. | Partial | Existing one-year service reminder dashboard retained. No new outbound AMC messaging. |
| Scheduled CA reports. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Notification history, retries and failure reporting. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |
| Per-company notification preferences and opt-in/opt-out controls. | Not implemented | Outbound automation/outbox/preferences/retries remain unimplemented. Provider credentials and scheduler are absent; profile explicitly shows unconfigured status. |

## Mobile and desktop evaluation

- Existing responsive web app retained; new forms use responsive grids and horizontally scrollable tables.
- No PWA manifest/service worker added. An offline cache must not store authenticated billing pages.
- No native Android/Windows builds, camera scanning, or desktop package were created.
- Current browser QA uses a desktop viewport. Physical printers and mobile devices were not tested.

## Activation gate

New purchasing/account schemas are not applied to the live database. New navigation is hidden until the additive setup is present. A dry-run/apply script is prepared; user approval is required before its live application. GitHub push and deployment have not occurred.

## Scope honesty

This is a substantial development increment, not completion of every master-checklist item. Not-implemented rows remain in the same consolidated task and must not be represented as finished or blocked solely by missing credentials.
