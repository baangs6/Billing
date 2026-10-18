# Adversarial review record

Fresh-context reviewers received the artifact paths and explicit safety contracts, without app imports, tests, credentials or database access. External cross-model CLI review was skipped to follow the user instruction to proceed without repeated review-choice prompts; no code was sent to an external CLI.

| Artifact / claim | Finding | Resolution / evidence |
|---|---|---|
| Returns preserve original tax/credit while note PDF reconciles | P2: note Credit column used allocated line total while note round-off used taxable + tax; partial paise returns could display inconsistent totals. Valid. | Credit column now displays taxable + tax. Regression returns one of two 2-paise items at 28%: 4-paise pre-round credit, -1-paise adjustment, 3-paise total. |
| Selective reset preserves unrelated financial history | P1: any purchase forced Inventory, which could force unrelated Invoices/Payments even for manual services. Valid. | Dependencies inspect actual product/stock links; service-only purchase reset regression preserves sales, receipts and inventory. Customer/supplier settlement partitions remain distinct. |
| Exact rate precision validation | P2: multiplication by 10^9 rounded very long Decimal input, accepting forbidden precision. Valid. | Validate original digits/exponent without context-rounded arithmetic; trailing-zero and long nonzero-tail regression cases. |
| Revised reset, PDF and rate fixes | No concrete findings in fresh source review. | Targeted tests: 18 passed before expanded unit integration. |
| Product units: UI and historical stock contract | P2: binary default-rate multiplication produced 0.028999999999999998; purchase alternate label retained primary text. Both valid. | BigInt decimal rate conversion, explicit original-unit choice for labels; Node arithmetic regression. |
| Revised unit, stock lifecycle and private photo paths | No concrete findings in fresh source review. | Integration tests and isolated browser/PDF verification recorded in VERIFICATION.md. |
| Large-value export/payment precision | Source review found remaining float formatting in dynamic report columns and UPI QR amount. Valid. | Decimal formatting throughout new exports/PDF quantities; large-paisa CSV regression and exact QR parameter test. |
| Product thumbnail metadata stripping | Automated test found JPEG comment survived PIL conversion. Valid. | Copy decoded pixels into a fresh image before encoding. Metadata regression passes. |

| Test isolation and rate-input resource bounds | Global WSGI import invoked inherited finance metadata setup; manual cleanup could be skipped after a shutdown/drop error. Rate zero with a huge exponent could expand during fixed formatting. Valid. | Disposable bootstrap DB before imports, nested cleanup finally blocks and injected-error regression; rates limited to 100 characters and canonical zero, with tests. |

| Revised manual cleanup | Nested finally ensures server shutdown, fixture finalization and bootstrap cleanup are each attempted. | Three injected-error cases pass; latest unit/safety suite: 12 passed. |

Source review is not a penetration test or proof of all runtime behavior. The full master checklist remains partial; unresolved capability gaps are recorded individually in FEATURE_PROGRESS.md.
