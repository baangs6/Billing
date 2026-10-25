# Referral rewards

Customers earn no welcome points. Select an existing company customer in the searchable Referred by field when adding a customer (including the billing popup). The referrer is locked after invoice history exists; self-referrals and cross-company identifiers are rejected.

One point is awarded to the referrer when the referred customer's first active invoice (creation order) is fully paid with recorded payments. A zero-value invoice or a credit note does not qualify. Later invoices and repeated submissions do not earn another point. This applies to new payment activity; existing historical payments are not backfilled.

Settings offers Fixed value per point (initial value zero, configure a positive INR amount before redemption) and Manual amount. Billing displays available points, including the current invoice's points when editing. Referral discount is combined with the common discount before GST and excludes additional charges. Both discounts appear separately on customer invoices and all supported PDF/thermal formats. Existing invoice discount values are preserved when the same points are retained in fixed mode after a setting change.

Saving, changing customers, editing points and cancellation update balances within the existing serialized company transaction. Failed writes roll back. Cancellation/Trash returns redeemed points once; restoring leaves the invoice cancelled. Selective invoice reset also returns points on active invoices if customers are retained. Full customer/company resets remove balances. Awarded-once markers survive invoice-only reset to prevent earning again.

Earned points remain earned after later payment corrections or refunds; there is no automatic negative balance or reward clawback. A customer cannot be moved off an invoice that already earned a referral reward. Customer profile history shows the latest 100 earn/redeem/return events, also retained in the audit trail. Existing permissions govern customer links, settings, invoice creation/editing and payments.

Verification: tests/test_referrals.py covers earning, first-invoice eligibility, replay, fixed/manual redemption, insufficient balance, rollback, edit, Trash/restore, self/invalid referrals, referrer locking, and customer PDF formats. No production records are used for tests.

Customer managers can add manual points from Customers > customer profile > Referral points history. A positive whole-number amount and a reason are required. Entries are tenant-scoped, transactional, audited, and protected against replay of the same submission. Manual awards are separate from the automatic first-paid-invoice award.
