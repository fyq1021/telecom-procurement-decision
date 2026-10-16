# From Partial Deliveries to an Exception Review List

**Synthetic case study · network equipment spare parts · review date: 13 October 2026**

## Problem

In my telecom procurement internship, I used ERP advanced filtering to locate orders by order number, checked order information, and printed purchase orders and goods-receipt forms from system templates. This independent case extends that document workflow to a hypothetical problem: one order arrives in multiple batches, with separate arrival records and signed receipts. To prepare a reliable follow-up list for a supervisor, the records need to show what has arrived, what is still missing, whether any batch arrived after the required date, and whether supporting documents agree. All records in this case are synthetic and do not describe the internship employer.

## Method

I built a small audit using only Python's standard library. It joins seven synthetic orders to arrival batches by `order_id`, then matches each batch to a signed receipt by `delivery_id` and `order_id`. The calculations use a fixed review date so another reader can reproduce the same status. Separately, the script checks `order quantity × unit price` against contract amount, signed quantity against delivered quantity, and whether required files are recorded as present. Fifteen unit tests cover on-time split deliveries, unfinished orders, late arrivals, over-delivery, missing dates and receipts, duplicate batch IDs, and unmatched records.

The main rules are straightforward: accumulate actual arrivals; never let outstanding quantity become negative; count only batches arriving after the required date as late; and assign a final delivery date only when recorded cumulative arrivals reach the ordered quantity. For an unfinished overdue order, overdue days are measured through the review date and the final delivery date remains blank.

## Findings and suggested follow-up

These are **designed example outcomes**, not estimates of how often such problems occur in a real company.

| Order | Audit finding on 13 October 2026 | Intern-level follow-up for supervisor review |
| --- | --- | --- |
| O-1001 | 100/100 received in two on-time batches; receipts and contract amount agree. | Mark the quantity check complete. |
| O-1002 | 30/80 received; 50 outstanding; required date not yet passed. Receipt for the first batch is missing. | Request the missing signed receipt; continue tracking the remaining 50. |
| O-1003 | 30/50 received; 20 outstanding; 10 arrived after the required date; running delay is 8 days. One receipt records 8 while the batch records 10. | Flag delayed balance and quantity discrepancy for verification. |
| O-1004 | 40/40 received three days after the required date. | Record actual completion and late arrival for review. |
| O-1005 | 35 received against 30 ordered, and contract amount differs from quantity × unit price. | Verify excess receipt and contract amount before reconciliation. |
| O-1006 | No arrival against 20 ordered; running delay is 12 days; contract file is marked missing. | Follow up on arrival and request the contract file. |
| O-1007 | 10/25 received, but the required date and a document flag are missing. | Obtain missing source information; leave due-date status pending review. |

These are prompts to investigate. The intern does not select a supplier, approve a payment, or decide whether an exception is acceptable.

## What this project demonstrates

The case connects operational records to a decision-ready review list: it makes assumptions visible, separates different exception types, keeps unknowns explicit, and checks the rules with tests. It also shows the ability to communicate technical findings in concise English. The Python implementation and all numbers are available in this repository.

## Limits

The dataset is synthetic and small by design; the counts above are not empirical performance rates. A recorded arrival does not prove technical acceptance or product quality. The model has no real supplier reliability history, procurement approval workflow, or international shipping data. It should therefore be presented as an independent audit prototype inspired by internship exposure to procurement documents, not as a deployed company system or evidence of achieved savings.
