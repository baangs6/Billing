# Business settings completion — 19 October 2026

Settings → Business profile & printing now provides GST registration visibility, multiple business types, industry/registration choices and up to ten validated custom header name/value pairs. Existing identity, logo, signature and print preferences are retained. New documents snapshot these settings; historical snapshots are never backfilled.

Settings → Account shows the registered owner, login email, registered company phone, subscription plan and dates. Profile → Switch business opens separate company memberships. Creating another business requests its own plan and starts PENDING; only software-owner approval activates it. Inventory, parties, invoices and subscriptions are not shared. Linked memberships cannot log in with internal addresses or change the root credentials. Root credential changes invalidate linked sessions.

Financial-year closing requires a protected COMPANY_ADMIN role, current login password, exact CLOSE FINANCIAL YEAR confirmation and a completed 31 March cutoff. It prevents historical financial insertion, edits, cancellation and opening-balance replacement. Balances and stock continue from existing ledgers; nothing is copied or deleted and no reopening control is provided. Service completion remains available because it does not alter financial values. Explicit permanent resets/deletion remain separate password-confirmed operations and intentionally bypass the period lock.

Permanent company deletion requires the same administrator/password boundary and exact DELETE BUSINESS confirmation. It removes only that company's operational records, subscription and memberships. Shared root credentials are rehomed to a surviving active membership, preserving its actual role. The existing company reset uses the same preservation rule for other administrators. Software-owner payment/audit records remain in the owner's books. Tests use disposable databases; no real company was closed or deleted.

Company headers and signatures flow into sales invoice formats, proposal/proforma/challan PDFs, purchases/orders and linked credit/debit-note PDFs. Notes use the original document's business snapshot. Non-GST documents do not acquire a GSTIN from later settings.

TDS/TCS remains disabled by user instruction until accountant confirmation. Subscription tax invoices remain unavailable until the software seller's legal/tax details are supplied. No email/SMS/WhatsApp service was enabled. Physical printer calibration is not covered by PDF rendering checks.
