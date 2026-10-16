# Telecom Procurement Order Audit

**Independent portfolio case · network equipment spare parts · Synthetic Data**

This small Python project turns purchase orders, partial delivery records, and signed receipts into an exception review list. It was inspired by document-checking work during a telecom procurement internship. The code was developed independently; it was **not used by the employer**. Every order, supplier reference, date, quantity, price, and outcome here is invented. No employer record or confidential data is included.

## Question and approach

When an order arrives in several batches, what quantity is still missing, what arrived late, and which supporting records need checking? The script joins the three synthetic CSV files by `order_id` and matches signed receipts to arrival batches by `delivery_id`. It then checks:

- cumulative arrivals, outstanding quantity, and excess quantity;
- quantity arriving after the required date, the actual completion date when known, and overdue days;
- contract amount against ordered quantity × unit price, signed receipts against batches, and document presence.

An unfinished order has no actual completion date. Missing or invalid source data leads to `待核查` (review required) instead of a guessed status. The output is for **supervisor review**, not purchase approval, supplier selection, or payment authorization.

## Reproduce the case

Use Python 3.10 or newer. No third-party packages are needed. In the repository directory, run:

```sh
python src/audit_orders.py --as-of 2026-10-13
python -m unittest discover -s tests -v
```

The first command writes `outputs/order_audit.json`; it never edits the input CSV files. The fixed `--as-of` date makes the example reproducible. For unfinished orders, the overdue status changes with the review date.

## Example finding

Order `O-1003` has 50 units ordered. Two recorded batches total 30 units, leaving 20 outstanding. Ten units arrived after the required date. On 13 October 2026 the unfinished order is 8 days overdue; `final_delivery_date` remains blank. One signed receipt records 8 units for a 10-unit batch, so it is flagged for verification. These figures are designed examples, **not measured supplier performance**.

Read the [English case study](docs/CASE_STUDY.md) for all seven scenarios. The [audit code](src/audit_orders.py), [synthetic input data](data/orders.csv), [tests](tests/test_audit_orders.py), and [sample output](outputs/order_audit.json) are available for inspection.

## Scope and limitations

This is a rule-based audit prototype with seven synthetic orders and 15 unit tests. It does not predict supplier risk or estimate real savings. Arrival records alone cannot establish technical acceptance or product quality. The portfolio value is in reproducible reconciliation, explicit handling of unknowns, and clear communication of follow-up items.
