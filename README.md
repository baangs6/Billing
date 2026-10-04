# Ledger — Billing & Inventory on MongoDB Atlas

The Flask/Jinja/JavaScript billing application now uses **MongoDB Atlas** through native PyMongo operations. SQLite is used only by the legacy import script; the running app does not open or write SQLite files.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

Alternatively run `./start.ps1`. Open http://127.0.0.1:5000. Migrated accounts retain their existing email and password. No default passwords are created.

## Owner panel and SaaS onboarding

The owner console is a **separate Flask service** on http://127.0.0.1:5001. The company app remains on port 5000. Run `python scripts/init_saas.py` once after installing dependencies, then `python admin_app.py` alongside `python app.py`. `start.ps1` initializes and starts both services.

The initializer preserves migrated workspaces as ACTIVE on an unlimited, non-expiring existing-workspace subscription. It seeds an editable Trial plan plus free-launch Subscription and Unlimited plans. Subscription defaults to 10 users, 5,000 products and 2,000 monthly finalized invoices; Unlimited removes all three quotas. Both launch plans cost zero monthly/yearly and have no trial days. These are editable launch settings, and subscription expiry still follows the assigned billing cycle. Plan prices and limits are configured by the owner; future plan edits retain existing assigned snapshots.

For the first owner, open the private link in `instance/admin-setup-url.txt` from this computer. The link expires after 24 hours and is consumed on account creation. Choose your name, email and password (14+ characters), then add the displayed setup key to a time-based authenticator such as Microsoft or Google Authenticator and enter its six-digit code. Save the eight one-use recovery codes. No owner credentials or default password are invented. Re-run the initializer to rotate an expired unused link; it never overwrites an existing owner.

Owner accounts have separate identities, cookie names, signing secrets, encrypted TOTP seeds, replay prevention, login throttling and server-side sessions that expire after two hours. Keep `instance/admin-encryption.key` and `instance/admin-session.key` private and backed up with deployment secrets. Losing the encryption key makes authenticator seeds unreadable. The default owner server binds to loopback; production access requires an HTTPS reverse proxy with separate hostnames and appropriate network access controls.

### Render admin deployment

Deploy a separate Python Web Service with build command `pip install -r requirements.txt` and start command `waitress-serve --host=0.0.0.0 --port=$PORT admin_app:app`. Set `MONGODB_URI`, `MONGODB_DATABASE`, `HTTPS=1`, `ADMIN_ENCRYPTION_KEY`, and `ADMIN_SESSION_KEY` in Render Environment. The admin login is `https://YOUR-ADMIN-SERVICE.onrender.com/login`.

When migrating the existing owner account, privately copy the contents of `instance/admin-encryption.key` into `ADMIN_ENCRYPTION_KEY`, and `instance/admin-session.key` into `ADMIN_SESSION_KEY`. Never post or commit these values. Keep them stable across deployments. The encryption key must match the key used to encrypt the existing owner's authenticator seed in MongoDB; a newly generated key cannot decrypt it. On Render, startup requires these environment variables instead of generating keys on an ephemeral filesystem. A wrong encryption key returns an actionable 503 message and grants no session. Retain the original files as a private backup.

To diagnose a failed login, inspect the admin service's Render Logs at the time of the request. `cryptography.fernet.InvalidToken` indicates a mismatched encryption key. A dashboard error involving `created_at` may indicate legacy company data; missing and null registration timestamps are supported. Other tracebacks require their specific cause to be addressed.

The console includes company search and pending approvals, approve/reject/review/suspend/reactivate/archive actions, company usage and users, plans, subscriptions, manual payment ledger, renewal review/rejection, audit history and registration/contact policy. It has no company impersonation or financial record deletion. Stored-byte usage is logical BSON size, not Atlas billed storage/index size.

New registrations collect company/owner details, an optional logo and requested plan, and stay PENDING until reviewed. Trial access begins on approval. Company screens include staff, configurable company roles, subscription details/payment history and renewal requests. COMPANY_ADMIN, MANAGER, BILLING_STAFF and INVENTORY_STAFF are seeded per tenant; owner-role permissions and the last active company administrator are protected.

Every operational request validates active identity/session version, company/subscription status, role permission and plan feature. Expiry is checked directly at request time; no background worker is required for enforcement. Pending, rejected, archived, suspended and expired accounts have status/subscription screens only. A plan with multiple users disabled restricts staff access while retaining user records.

Plan assignments store immutable snapshots. Editing or disabling a plan does not alter current subscribers. Blank limits mean unlimited; zero means no allowance. Active-user/product quotas and monthly first-finalization invoice quotas are enforced inside the company write transaction. Invoice retries, edits and cancellation do not reclaim or consume additional quota. The monthly period uses Asia/Kolkata. Calendar-based renewals extend from the later of now and valid expiry. An explicit expiry date includes that whole date in IST. Renewing a suspended company retains suspension until explicit reactivation.

Disabling inventory blocks tracked-product billing; free-text nonstock invoices remain available. Enabling inventory after a disabled period requires physical stock correction through Inventory and explicit confirmation in Settings before tracked billing resumes. Subscription payments are actual manually verified receipts with duplicate-submission protection and remain separate from invoice payments. Recording a receipt does not automatically approve or renew access.

## Private configuration

The local installation reads `instance/mongodb.env`, ignored by Git. It contains `MONGODB_URI` and `MONGODB_DATABASE=ledger_billing`. `.env.example` has placeholders only. Environment variables override this file; `BILLING_ENV_FILE` can select another private file. The browser never receives database credentials. Allow only backend IP addresses in Atlas, use TLS, and store deployment credentials in a secret manager.

This installation is already initialized and migrated. For a new empty database, run:

```powershell
python -c "from mongo_store import MongoBackend,load_configuration; b=MongoBackend(*load_configuration()); b.initialize(); b.client.close()"
```

## Storage and financial consistency

`mongo_store.py` provides tenant-scoped access, schema validation, unique indexes, counters and transactions. Collections include businesses, users, settings, customers, categories, products, inventory, movements, invoices, items, payments, audits and submission tokens. Every business-owned record including child documents has `business_id`. Query filters derive it from the authenticated session. Route validation verifies linked customers/products/invoices belong to that business. MongoDB has no SQL foreign keys or PostgreSQL-style row-level security; the repository and application authorization are essential isolation controls.

Money is exact **BSON Int64 paise**; quantities are integer thousandths. No binary floating-point money is stored. Python Decimal calculations with half-up rounding remain authoritative. Prices exclude GST, discounts precede tax, CGST/SGST halves round independently, and IGST applies to inter-state invoices. Historical invoices preserve company, customer and item snapshots.

All business mutations use multi-document transactions with snapshot reads and majority writes. A company lock document serializes writes within that company, preventing simultaneous overselling and overpayment. The driver retries transient transactions and uncertain commits. Sessions/flash messages restore before retry. GET pages/PDFs use snapshot transactions so they cannot mix invoice revisions.

Submission tokens prevent duplicate invoices. Version checks prevent stale edits. Stock reversals, new movements, invoice updates and payments commit together or roll back. Paid invoice cancellation remains blocked until refunds/credit notes exist. Customer archive and product deactivation preserve financial links. PDF export uses ReportLab with A4 pages and repeated table headings.

## Legacy import and backups

`scripts/migrate_to_mongodb.py` backs up and reads `instance/billing.db`, validates references, imports records in one transaction and verifies every imported field. Existing IDs, password hashes and financial values are retained. It refuses a nonempty destination except to verify a recorded identical import. It never overwrites active business data. The original SQLite file and pre-migration source remain under ignored `instance/` as recovery material; there is no SQLite runtime fallback.

Atlas Free has no provider-managed backups. `python scripts/backup_mongodb.py` produces a consistent BSON-aware snapshot in private `instance/backups/`. Restrict access because it includes account password hashes and business data. Keep protected offsite copies and test restoration. No offsite destination has been configured automatically.

## Verification

```powershell
python -m pytest -q
```

Tests use actual Atlas transactions in a randomly named `ledger_test_*` database and delete only that generated test database afterward. They never clear `ledger_billing`. Credentials need permission to create/delete the test database. Tests cover calculations, invoice edits/cancellations, rollback, payments, snapshots, stale edits, duplicate submission, CSRF, tenant filters, registration, pages/exports and concurrent stock/payment writes. No mocked database substitutes for transaction tests.

For PDF visual QA, install `requirements-dev.txt` and run `python tests/visual_review.py`.

## Deployment and current scope

Use an HTTPS reverse proxy, `HTTPS=1`, a deployment-secret `SECRET_KEY`, operational logging and monitored backups. Frontend/backend hosting is separate from Atlas. Watch free-cluster storage and throughput limits before expanding production usage.

The current app includes business-isolated billing workspaces and the owner/company SaaS controls above. `SAAS_MONGODB_ARCHITECTURE.md` describes this implementation; `SAAS_ARCHITECTURE.md` retains the earlier PostgreSQL proposal for historical context.

Automated email verification, gateway checkout, automatic renewals/expiry notifications, credit notes/refunds, GST submissions, IRNs/e-way bills and purchase workflows are not implemented. Owner recovery codes recover the second factor, not a forgotten password. Company approval and payment verification are manual. Separate least-privilege Atlas runtime credentials, HTTPS/public deployment, offsite backup and restoration testing remain deployment work.

## Public home page

Anonymous visitors to `/` see the public Ledger home page with customer login, company registration and current active plans. Signed-in customers retain their dashboard at `/`; `/home` always displays the public page. Plan links preselect the registration plan, and the owner's registration policy controls signup availability. Product illustrations contain labeled sample data.

## Proposals / quotations

Open Proposals in the company sidebar, then Create proposal. Select a customer, title, validity date, product or manual-service items, tax treatment, scope and terms. Save a draft or record SENT, ACCEPTED or DECLINED manually. These statuses do not send email or imply electronic acceptance. PDF downloads identify the document as a proposal rather than a tax invoice.

Proposals use the same server Decimal/paise calculations and tenant scoping as invoices, with snapshotted customer/company/item details, optimistic edit versions, unique tenant proposal numbers and submission protection. Saving or editing a proposal does not change stock, create payments, or consume the monthly finalized-invoice quota.

Review & convert to invoice opens the existing billing form for confirmation and editing. Actual invoice saving rechecks subscription, GST, monthly quota, active customer/products, available stock and proposal revision. The proposal links to the resulting invoice only when that transaction commits. A failed finalization leaves the proposal unconverted; retries cannot convert it twice. Declined or expired proposals must be revised before conversion, and converted proposals are locked. Any scope/prices edited during finalization are preserved on the invoice; the original quotation remains unchanged.

Proposal read/create/edit permissions reuse invoice.view / invoice.create / invoice.edit, and proposal PDF downloads require the plan PDF feature. Company Admin and Billing Staff can create proposals; Managers can view them. Draft proposals are not inventory reservations.

## Password recovery

Both company and owner sign-in pages include Forgot password. Configure SMTP_HOST, SMTP_PORT (587), SMTP_FROM, SMTP_USERNAME and SMTP_PASSWORD in Render Environment, plus PUBLIC_BASE_URL on the company service and ADMIN_PUBLIC_BASE_URL on the admin service (their HTTPS origins). SMTP uses STARTTLS with certificate verification. Keep passwords private. Until configured, recovery shows an explicit unavailable message and disables sending; no reset URLs are exposed in pages or logs.

Links expire after 30 minutes, contain a random token stored only as a hash, and can be consumed once. Reset requests return the same message for known and unknown active accounts and are rate limited. Password updates and token consumption are transactional, invalidate existing sessions and outstanding links, and preserve owner MFA. Resetting a password does not activate an inactive account or change company approval/subscription status. This feature needs a working SMTP provider before clients can receive recovery emails.
