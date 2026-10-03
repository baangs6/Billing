# Earlier PostgreSQL SaaS proposal — superseded for the implemented MongoDB panel

> The owner selected MongoDB Atlas and subsequently requested creation of the admin panel. The implemented MongoDB design is in `SAAS_MONGODB_ARCHITECTURE.md`; see README.md for capabilities, startup and remaining deployment/email integrations. The PostgreSQL-specific proposal below is historical and does not describe the running services.

This document is the original proposal, not the current implementation feature list. The application now uses Flask, Jinja, JavaScript and MongoDB Atlas, with separate company and owner services.

## 1. Complete system architecture

Keep the responsive Jinja/HTML/CSS/JavaScript interface and Flask backend. Replace the monolithic backend with an application factory, domain services and separate route modules. Use SQLAlchemy for data access and Alembic for versioned migrations. Use PostgreSQL as the production database, with tenant row-level security (RLS), composite foreign keys and explicit application authorization.

Deploy two Flask services from the same repository: the company application and the Super Admin application. They have separate route registrations, authentication tables, session secrets, session stores, database credentials and cookies. In production use `app.example.com` for companies and `admin.example.com` for the owner. Do not share parent-domain cookies. On local development they use separate ports and distinct cookie names.

The public company service exposes registration, available plans, company login and verification/recovery flows. Its authenticated tenant application covers dashboard, billing, invoices, customers, products, inventory, payments, reports, settings, users and subscription status. The Super Admin service covers platform administration only. It does not register tenant billing routes or support silent company impersonation.

Supporting components:

- HTTPS reverse proxy and Waitress application servers.
- PostgreSQL on a private connection, with distinct migration, company-runtime and admin-runtime database roles.
- Redis for opaque server-side sessions, shared login throttling and background-job coordination.
- A worker for scheduled expiry reconciliation, operational notifications and larger exports. Request-time checks remain authoritative if the worker is delayed.
- Private storage for logos, signatures and generated exports; files use company-specific namespaces and authorized downloads or short-lived links.
- Email delivery for verification, recovery, approval notifications and renewal notices. Provider credentials are configured at deployment; local development uses a mail capture service. No live messages are sent merely by implementing this proposal.
- Monitoring, structured logs, automated backups and tested restoration.

Registration approval and subscription payment collection are separate decisions. Initially support manual owner-recorded subscription payments and renewal requests. There is no simulated payment checkout. A gateway integration is a subsequent explicitly configured step, with verified signatures and idempotent webhook processing.

## 2. Multi-tenant relational database schema

Use UUID primary keys; UTC timestamps; date fields for invoice dates; `NUMERIC(18,2)` for money; `NUMERIC(18,3)` for quantities; and constrained decimal tax rates. Calculations use Python Decimal and half-up rounding. Monetary limits and quantities are validated before storage.

Platform tables:

| Table | Main columns and relationships |
|---|---|
| companies | id, name, owner_name, phone, contact_email, address, state, pin, gstin, business_type, requested_plan_id, status, registered_at, approved_at, approved_by, rejection_reason, archived_at |
| company_users | id, company_id, name, normalized_email, password_hash, role_id, active, verified_at, last_login_at, session_version, created_at |
| roles | id, company_id, name, protected_owner_role, active |
| permissions | id, unique immutable permission code, description; global catalogue |
| role_permissions | company_id, role_id, permission_id; unique role/permission pair |
| admin_users | id, normalized_email, password_hash, active, MFA secret stored encrypted, recovery-code hashes, last_login_at, session_version |
| subscription_plans | id, name, description, monthly_price, yearly_price, trial_days, active, archived_at |
| plan_versions | id, plan_id, version, published_at; immutable version of prices and plan rules |
| feature_entitlements | plan_version_id, feature_code, enabled, numeric_limit; unique version/feature pair |
| subscriptions | id, company_id, plan_version_id, status, billing_cycle, start_at, expiry_at, trial_start_at, trial_end_at, agreed_amount, currency, payment_status, created_at |
| subscription_payments | id, company_id, subscription_id, amount, method, reference, paid_at, status, external_event_id, recorded_by; append-only payment records |
| renewal_requests | id, company_id, requested_plan_id, billing_cycle, status, submitted_at, reviewed_by, notes |
| company_approvals | id, company_id, admin_id, action, previous_status, new_status, reason, created_at |
| admin_audit_logs | id, admin_id, company_id nullable, action, entity_type, entity_id, previous_value, new_value, IP, device/user-agent, request_id, created_at |
| platform_settings | registration policy, trial policy, renewal contact, notification preferences; secrets held in the deployment secret manager |
| verification_tokens | user_id, company_id, hashed_token, purpose, expires_at, consumed_at |
| notification_outbox | company_id nullable, event_type, recipient, delivery_status, attempt_count, created_at; worker consumes committed events |

Financial and operational tables:

| Table | Main columns and relationships |
|---|---|
| business_settings | company_id, invoice format, invoice sequence policy, GST settings, negative-stock policy, terms, bank/UPI details, signature/logo file IDs |
| customers | id, company_id, contact/address/GST fields, notes, archived_at |
| categories | id, company_id, name; unique company/category name |
| products | id, company_id, category_id, SKU, name, description, purchase_price, MRP, selling_price, GST rate, HSN, unit, minimum_stock, active |
| inventory | company_id, product_id, quantity, version; unique company/product balance |
| stock_movements | id, company_id, product_id, invoice_id nullable, signed_quantity, reason, actor_user_id, created_at |
| invoices | id, company_id, customer_id, number, date, type, status, decimal totals, customer/business snapshots, optional service/installation dates, version, created_by |
| invoice_items | id, company_id, invoice_id, product_id nullable, name/HSN/unit/price/GST snapshots, quantity, discount, taxable_amount, tax, total |
| payments | id, company_id, invoice_id, amount, date, method, reference, notes, created_by; separate company-customer payment ledger |
| invoice_revisions | id, company_id, invoice_id, revision, old/new snapshots, actor, reason, created_at |
| idempotency_keys | company_id, operation, key, request_hash, result_record_id, created_at; unique company/operation/key |
| company_audit_logs | id, company_id, user_id, action, entity, old/new values, request metadata, created_at |
| files | id, company_id, private storage key, purpose, MIME type, byte_size, created_by, archived_at |
| usage_counters | company_id, period_start, invoice_count; row locked during quota enforcement |

Tenant safety invariants:

- Every company-owned row has a non-null `company_id`, including child records, exports, files and background-job inputs.
- Tenant parent tables have a unique `(company_id, id)` key. Child references use composite foreign keys such as `(company_id, invoice_id) → invoices(company_id, id)`. A Company A payment cannot reference a Company B invoice even if application code makes a mistake.
- The user's role must belong to the same company through a composite foreign key. Tenant roles can reference only company permission codes, never platform admin permissions.
- SKU and invoice numbers are unique within a company. Every tenant index begins with `company_id` where appropriate, followed by common search/date/status fields.
- Only one current subscription per company is allowed. Historic subscriptions and payments remain available; date/status checks prevent overlapping active periods.
- Status, amount, quantity, date and cycle constraints validate database writes. Retained financial records use restrictive foreign keys rather than cascading deletion.
- Company runtime queries run with RLS enabled and forced on tenant tables. The runtime database role is neither a table owner, a superuser, nor a BYPASSRLS role. Policies constrain both reads and writes. Missing tenant context denies access. Whole-table privileges such as TRUNCATE are withheld.
- Each request opens a transaction and sets its tenant context transaction-locally only after validating the authenticated user. Connection pooling cannot retain another request's tenant context. Workers follow the same rule.
- Admin database credentials have narrow access to platform records and approved usage views, not unrestricted invoice/customer tables. Platform-wide usage views return counts and byte totals, not business invoice content. Any later support access would require a separately approved, explicit and audited workflow.

Company-user login resolves an account by verified normalized email; keep global uniqueness for company login emails for this version. Supporting one email with memberships in several companies would require a separate identity/membership model and a verified workspace picker; it is outside this proposal's initial scope.

## 3. Super Admin architecture

Separate login, mandatory MFA, no public admin registration, and no default password. Bootstrap the first software-owner account using a local management command with hidden password input. Recovery codes are shown once and stored hashed. The Super Admin role is never a selectable company role.

Navigation and pages:

- Dashboard: company counts by status, trial subscriptions, total company users, new companies this month, actual subscription collections this month, recent registrations, expiring subscriptions.
- Companies: all, pending, active, suspended, expired and rejected; search name/phone/email and filter status/plan/registration/expiry dates.
- Company detail: registration/profile, approval history, current and historical subscriptions, users, last login, invoice/product/customer counts and uploaded-file storage bytes. Company archives preserve data.
- Subscriptions: current, trials, expiring soon, expired; renew/extend, set expiry, change plan, suspend/cancel. Record reasons and previous/new values.
- Plans: create, edit by publishing a new version, activate or disable. Disabling prevents new selection but does not silently break existing subscribers. Existing entitlements change only through an explicit audited assignment to a new plan version.
- Users: company-user directory and activity. No password retrieval or unlogged impersonation.
- Payments: actual software subscription payments, references and payment status. This is separate from customer invoice collections.
- Audit logs: filters for administrator, company, action and timestamp.
- System settings: onboarding, trial, renewal contact and notifications. Credentials stay outside editable database settings.

Metric definitions are explicit: revenue cards initially show collected subscription payments, not estimated recurring revenue or total tenant sales. Trial counts come from subscription status; an approved trial company's company status is ACTIVE.

## 4. Company Admin architecture

Company Admin owns the tenant workspace. They can manage their company profile, customers, catalogue, inventory, billing, payments, reports, staff, role permissions, subscription view and renewal requests, subject to the purchased plan.

Additional pages are Company Users, Roles & Permissions, and Subscription. Existing business pages are reused after routing all operations through tenant-aware services. The subscription page shows plan rules, current usage, trial/expiry dates, payment history and a working renewal request form.

Pending accounts can sign in to a limited status page with: “Your account is awaiting administrator approval.” Rejected, suspended and expired users see an appropriate explanation without access to tenant operations. Expired Company Admins can reach renewal and subscription details. Rejection and renewal contact information is provided where appropriate.

No company user can edit company approval status, subscription entitlements, plan prices, platform settings or their own platform privilege. Company Admin cannot deactivate the last active Company Admin or accidentally remove their own only recovery path.

## 5. User roles and configurable permissions

Seed the following defaults per company; allow Company Admin to create/customize tenant roles without granting permissions outside the company permission catalogue or their own permitted scope.

| Capability | Company Admin | Manager | Billing Staff | Inventory Staff |
|---|---|---|---|---|
| Company profile/settings | Manage | — | — | — |
| Company users/role permissions | Manage | — | — | — |
| Customers | Manage | Manage | View/select | — |
| Products | Manage | View | View/select | Manage |
| Inventory | Manage | View | Availability only | Manage |
| Invoices | Create/view/edit/cancel | View | Create/view | — |
| Customer invoice payments | Record/view | View | Record/view | — |
| Reports | View/export | View/export | — | — |
| Subscription/renewal requests | Manage requests | — | — | — |

Use granular codes such as `invoice.create`, `invoice.edit`, `invoice.cancel`, `payment.record`, `product.manage`, `inventory.adjust`, `report.view`, `report.export`, `user.manage`, and `role.manage`. Permission checks are evaluated on every request and again in the domain service. Navigation derives from the same rules.

Effective access = authenticated active user AND permitted company/subscription state AND role permission AND plan entitlement AND available quota. A role cannot unlock an unpurchased feature.

## 6. Company approval workflow

Public registration collects company/shop name, owner name, phone, email/password, address, state, PIN, optional GSTIN/logo, business type and requested active plan. Validate and atomically create company status PENDING, its Company Admin and settings. No trial/paid access period begins while approval is pending.

Registration appears in the owner's Pending Approvals queue. Email verification is required before approval. The owner reviews details, requested plan and notes. Approval changes PENDING → ACTIVE, records approved administrator/time/notes and starts the chosen trial or paid subscription. A payment prerequisite can be enforced for paid activation.

Rejection requires a reason and changes PENDING → REJECTED while preserving registration and history. Reconsideration uses an explicit audited return-to-review action, never a silent status overwrite. Suspension/reactivation also requires notes and validates subscription eligibility. Reactivating an expired company requires renewal or a valid replacement subscription.

Duplicate approve/reject requests are idempotent. Approval, subscription creation, audit event and notification-outbox event commit in one transaction.

## 7. Subscription workflow and feature control

Plans are configured in the panel, not hard-coded. Versioned rules include monthly/yearly price, trial days, maximum active users, invoices finalized per calendar month, maximum active products, inventory, GST, reports, PDF exports, multiple users and additional feature codes.

Use the company timezone (initially Asia/Kolkata) for monthly invoice quotas and reporting periods. Quota definition: each distinct invoice first finalized during that calendar month consumes one slot; editing/retrying does not consume another slot and cancellation does not refund a slot. A duplicate saved as a new invoice consumes another slot. Active-product and active-user limits count active records. Zero is a zero allowance; null explicitly means unlimited.

Subscriptions use TRIAL, ACTIVE, EXPIRED, CANCELLED or SUSPENDED. Company approval status and subscription status remain separate. The application checks time boundaries on every request. A scheduled worker reconciles display statuses and sends configured expiry notices, but access never depends on a worker running on time.

Use exclusive expiry timestamps: access ends at `expiry_at`. Date-based expiry selected in the panel is translated to the following midnight in the company timezone. Trial access ends at the earlier applicable boundary. Paid renewals extend from the later of now and the valid existing expiry, using calendar months/years rather than assuming every month has 30 days.

Expired accounts preserve all data and display: “Your subscription has expired. Please renew your subscription.” Initially block tenant operations while permitting Company Admin subscription/renewal screens, account recovery and sign-out. No business-data export escape through an unguarded endpoint.

Renewal flow: Company Admin submits a request → owner verifies payment/terms → owner records subscription payment and renews/extends → audit and notification recorded → access resumes. No automatic activation from an unverified browser payment claim.

Plan changes specify the effective version/time and price. Downgrades preserve existing records and block further creation when over quota; they do not remove users/products/invoices. Owner sees usage warnings before applying the downgrade. Feature-disabled stock quantities are not changed by invoices; enabling inventory requires an explicit stock reconciliation step before tracked billing.

Quota enforcement locks a company counter/appropriate rows in the same transaction as creation, preventing simultaneous requests from exceeding a plan limit. Export, GST creation, staff management and inventory endpoints all enforce features on the backend.

## 8. Invoice and inventory workflow

Resolve tenant and permissions, check subscription/features/quota, load only that tenant's customer/products and validate inputs. Prices exclude tax; line discounts apply before tax. Decimal calculations produce snapshotted amounts. Split intra-state tax into independently rounded CGST/SGST; use IGST for inter-state invoices. Preserve company/customer/item snapshots.

Saving locks invoice numbering, quota counters and stock rows in consistent product-ID order. Number allocation, invoice/items, initial payment, stock movements, revision/audit and idempotency result commit together. A failed step rolls everything back. Reusing an idempotency key with different request data is rejected.

Editing uses optimistic invoice versions plus row locks. Compare aggregated old/new product quantities and apply only net stock changes. Validate against existing payments and retain the complete prior revision. Payments stay separate and cannot exceed the balance. Cancel an unpaid invoice once, preserve its number/history and restore tracked stock once. Continue blocking cancellation of paid invoices until a reviewed refund/credit-note module exists.

PDFs, reports, CSVs, printing and downloads run through the same tenant/permission/entitlement guards as normal pages. Background exports revalidate the account when executing and downloading. Multi-page A4 rendering uses stored snapshots. Share links, if introduced, must be signed, scoped, expiring and revocable; there is no publicly accessible invoice-ID URL.

## 9. Security model and validation

- Derive company context from the authenticated database user; never accept a posted tenant/company ID as authority. Super Admin operations use a separate authenticated admin identity and explicit company action.
- Independent opaque sessions for the two services; secure HttpOnly host-only cookies, SameSite policy, session rotation, expiry and revocation through session versions. Admin logout/session revocation has no dependence on company sessions.
- Strong password hashes, company email verification, hashed single-use recovery tokens, mandatory admin MFA and protected recovery. No stored/retrievable plaintext passwords.
- Shared login throttling by account and IP, with monitoring and generic login errors. Public user registration never creates an admin or accepts a privileged role parameter.
- CSRF protection for mutations, server-side field validation, parameterized SQL/ORM queries, output escaping, restrictive headers and safe error pages. Allowlisted request fields prevent mass assignment.
- Upload size/dimension/MIME validation and image re-encoding. Tenant-scoped private files; no executable uploads, public signatures or shared storage keys.
- Append-only approval, subscription, payment and audit history. Runtime roles cannot update/delete audit records. Business archival retains records; expiry never deletes data.
- Audit admin actions with identity, company, old/new values, time, IP and user-agent; exclude passwords, secrets and recovery tokens from logs.
- Private database access, least privilege, managed secrets, backups and restore tests. Company users never receive database credentials.
- Automated adversarial tests for Company A/B reads/writes/joins/downloads, role escalation, disabled features, pending/suspended/expired access, concurrent quota/stock updates, transaction-context leakage and forged company IDs. Test RLS using the actual restricted PostgreSQL runtime role, not a migration/table-owner connection.

RLS is defense in depth for application query mistakes; it is not a substitute for preventing SQL injection or protecting runtime credentials. Platform administrators are trusted operators, but administrative business-data access is deliberately separated and limited.

## 10. Recommended project structure

```text
billing-saas/
  app/
    __init__.py                  # separate company/admin app factories
    config.py
    extensions.py
    company_wsgi.py
    admin_wsgi.py
    models/
      platform.py
      identity.py
      billing.py
      inventory.py
    company/
      auth/                     # registration/login/verification/recovery
      dashboard/
      customers/
      products/
      inventory/
      invoices/
      payments/
      reports/
      settings/
      users/
      subscriptions/
    admin/
      auth/
      dashboard/
      companies/
      plans/
      subscriptions/
      users/
      payments/
      audit/
      settings/
    services/
      tenant_context.py
      authorization.py
      approvals.py
      entitlements.py
      subscriptions.py
      usage.py
      invoice_calculation.py
      invoice_lifecycle.py
      stock.py
      pdf.py
      files.py
      audit.py
    tasks/
      expiry.py
      notifications.py
      exports.py
    templates/
      public/
      company/
      admin/
      shared/
    static/
  migrations/                   # schema, constraints, RLS policies
  tests/
    unit/
    integration/
    security/
    browser/
  scripts/
    bootstrap_admin.py
    import_legacy.py
    backup_restore.py
  deploy/
    compose.yaml
    reverse-proxy/
  docs/
  .env.example                  # names only; no real secrets
  requirements.txt
  README.md
```

## Implementation sequence after approval

1. Build the new tenant-first PostgreSQL schema, constraints, RLS policies, factories and migrations; establish tests using isolated test companies.
2. Implement separate company/admin identity, MFA, verification, recovery and session controls.
3. Implement configurable plans, pending registration, approval, status pages and admin dashboard.
4. Implement subscriptions, payments, renewal requests, entitlements and atomic quotas.
5. Implement company roles/staff and connect existing billing/inventory/customer/product workflows to tenant-aware services.
6. Connect PDFs/reports/uploads, audit trails, background jobs and operational settings.
7. Run cross-tenant and concurrency tests, browser workflows, backup/restore checks and deployment verification.

Preserve the current SQLite database unchanged as the legacy source. After validating the new application, import each existing business as a company through an explicit reviewed migration, preserving invoices, payments, product snapshots and stock movements. Existing account approval, plan and expiry assignments must be reviewed rather than silently granting a permanent subscription. Compare counts, amounts and inventory balances before cutover; keep rollback available. The new SaaS runtime will not use SQLite as a fallback that disables RLS.

## Documentation consulted

- PostgreSQL row-level security: https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- PostgreSQL exact numeric types: https://www.postgresql.org/docs/current/datatype-numeric.html
- Flask modular route blueprints: https://flask.palletsprojects.com/en/stable/blueprints/

Decision requested: approve this architecture, including PostgreSQL, separately authenticated company/admin services, mandatory Super Admin MFA, manual subscription collection with renewal requests initially, and controlled migration of the existing database.
