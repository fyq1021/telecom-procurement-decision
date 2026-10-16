"""Audit synthetic purchase orders and partial deliveries with Python's standard library.

This script produces a review report. It does not approve suppliers or purchases.
"""

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def nonnegative_int(value):
    try:
        number = int(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def money(value):
    try:
        result = Decimal(value)
        return result if result.is_finite() and result >= 0 else None
    except (TypeError, InvalidOperation):
        return None


def parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def check_contract(order):
    quantity = nonnegative_int(order.get("order_qty"))
    unit_price = money(order.get("unit_price"))
    contract_amount = money(order.get("contract_amount"))
    if quantity is None or quantity == 0 or unit_price is None or contract_amount is None:
        return "待核查"
    return "一致" if unit_price * quantity == contract_amount else "金额不一致"


def check_receipts(deliveries, receipts):
    if not deliveries:
        return "待核查" if receipts else "暂无到货"
    by_delivery = defaultdict(list)
    for receipt in receipts:
        by_delivery[receipt.get("delivery_id", "")].append(receipt)
    delivery_ids = {delivery.get("delivery_id", "") for delivery in deliveries}
    if set(by_delivery) - delivery_ids:
        return "数量或订单不一致"
    missing = False
    for delivery in deliveries:
        matched = by_delivery.get(delivery.get("delivery_id", ""), [])
        if len(matched) != 1:
            missing = True
            continue
        receipt = matched[0]
        if receipt.get("receipt_file_present") != "Y":
            missing = True
            continue
        if receipt.get("order_id") != delivery.get("order_id"):
            return "数量或订单不一致"
        signed = nonnegative_int(receipt.get("signed_quantity"))
        delivered = nonnegative_int(delivery.get("quantity"))
        if signed is None or delivered is None:
            missing = True
        elif signed != delivered:
            return "数量或订单不一致"
    return "待核查" if missing else "一致"


def check_documents(order, receipt_status):
    flags = [order.get("contract_file_present"), order.get("purchase_order_file_present")]
    if "N" in flags:
        return "待补件"
    if any(flag not in ("Y", "N") for flag in flags):
        return "待核查"
    if receipt_status == "待核查":
        return "待补件或核查签收单"
    if receipt_status == "数量或订单不一致":
        return "待核查"
    if receipt_status == "暂无到货":
        return "现有资料齐备；签收单待到货"
    return "齐备"


def audit_one(order, deliveries, receipts, as_of):
    order_id = order.get("order_id", "").strip()
    quantity = nonnegative_int(order.get("order_qty"))
    due = parse_date(order.get("due_date"))
    issues = []
    warnings = []
    if quantity is None or quantity == 0:
        issues.append("订单数量缺失或无效")
    if due is None:
        issues.append("要求到货日期缺失或无效")

    valid_deliveries = []
    delivery_ids = set()
    delivery_data_problem = False
    future_delivery_count = 0
    for row in deliveries:
        delivery_id = row.get("delivery_id", "")
        arrival = parse_date(row.get("arrival_date"))
        count = nonnegative_int(row.get("quantity"))
        if not delivery_id or delivery_id in delivery_ids or arrival is None or count is None or count == 0:
            issues.append("到货记录缺失、重复或无效")
            delivery_data_problem = True
            continue
        delivery_ids.add(delivery_id)
        if arrival > as_of:
            future_delivery_count += 1
            continue
        valid_deliveries.append((arrival, delivery_id, count))
    if future_delivery_count:
        warnings.append("核查日之后的到货记录未计入；请核查是否误录为实际到货")
    valid_deliveries.sort()
    cumulative = sum(item[2] for item in valid_deliveries)
    outstanding = max(quantity - cumulative, 0) if quantity is not None and not delivery_data_problem else None
    excess = max(cumulative - quantity, 0) if quantity is not None and not delivery_data_problem else None
    late_arrival_qty = (sum(count for arrival, _, count in valid_deliveries if arrival > due)
                        if due and not delivery_data_problem else None)

    # Completion occurs on the first date cumulative arrivals reach order quantity.
    # An incomplete order has no factual final delivery date.
    final_delivery_date = None
    if quantity and cumulative >= quantity and not delivery_data_problem:
        running = 0
        for arrival, _, count in valid_deliveries:
            running += count
            if running >= quantity:
                final_delivery_date = arrival
                break
    if due is None or quantity is None or issues:
        delivery_status = "待核查"
        overdue_days = None
    elif cumulative > quantity:
        delivery_status = "超量交付"
        overdue_days = max((final_delivery_date - due).days, 0)
    elif cumulative == quantity:
        delivery_status = "全部完成"
        overdue_days = max((final_delivery_date - due).days, 0)
    elif as_of > due:
        delivery_status = "部分交付已逾期" if cumulative else "未到货已逾期"
        overdue_days = (as_of - due).days
    else:
        delivery_status = "部分交付未逾期" if cumulative else "未到货未逾期"
        overdue_days = 0

    # A completed order may ALSO be a normal split delivery. Keep two dimensions.
    normal_split_delivery = (
        delivery_status == "全部完成"
        and len(valid_deliveries) > 1
        and late_arrival_qty == 0
    )
    # A historical review must not require signed receipts for later arrivals.
    future_ids = {row.get("delivery_id") for row in deliveries
                  if (parse_date(row.get("arrival_date")) or date.min) > as_of}
    relevant_deliveries = [row for row in deliveries if row.get("delivery_id") not in future_ids]
    relevant_receipts = [row for row in receipts if row.get("delivery_id") not in future_ids]
    receipt_status = check_receipts(relevant_deliveries, relevant_receipts)
    return {
        "order_id": order_id,
        "delivery_status": delivery_status,
        "normal_split_delivery": normal_split_delivery,
        "ordered_qty": quantity,
        "cumulative_delivered_qty": cumulative if not delivery_data_problem else None,
        "outstanding_qty": outstanding,
        "excess_qty": excess,
        "late_arrival_qty": late_arrival_qty,
        "final_delivery_date": final_delivery_date.isoformat() if final_delivery_date else None,
        "overdue_days": overdue_days,
        "contract_amount_check": check_contract(order),
        "receipt_check": receipt_status,
        "documents_check": check_documents(order, receipt_status),
        "issues": issues,
        "warnings": warnings,
        "future_delivery_records_excluded": future_delivery_count,
    }


def audit_orders(orders, deliveries, receipts, as_of):
    grouped_deliveries = defaultdict(list)
    grouped_receipts = defaultdict(list)
    known_ids = {row.get("order_id", "").strip() for row in orders}
    counts = defaultdict(int)
    delivery_id_counts = defaultdict(int)
    for order in orders:
        counts[order.get("order_id", "").strip()] += 1
    for row in deliveries:
        grouped_deliveries[row.get("order_id", "").strip()].append(row)
        if row.get("delivery_id"):
            delivery_id_counts[row["delivery_id"]] += 1
    for row in receipts:
        grouped_receipts[row.get("order_id", "").strip()].append(row)
    results = []
    for order in orders:
        order_id = order.get("order_id", "").strip()
        result = audit_one(order, grouped_deliveries[order_id], grouped_receipts[order_id], as_of)
        if not order_id or counts[order_id] != 1:
            result["delivery_status"] = "待核查"
            result["normal_split_delivery"] = False
            result["final_delivery_date"] = None
            result["overdue_days"] = None
            result["issues"].append("订单编号缺失或重复")
        if any(delivery_id_counts[row.get("delivery_id", "")] > 1
               for row in grouped_deliveries[order_id] if row.get("delivery_id")):
            result["delivery_status"] = "待核查"
            result["normal_split_delivery"] = False
            for field in ("cumulative_delivered_qty", "outstanding_qty", "excess_qty",
                          "late_arrival_qty", "final_delivery_date", "overdue_days"):
                result[field] = None
            result["issues"].append("到货批次编号在多笔记录中重复")
        results.append(result)
    unmatched = [
        {"record_type": "delivery", "order_id": row.get("order_id"), "record_id": row.get("delivery_id")}
        for row in deliveries if row.get("order_id", "").strip() not in known_ids
    ] + [
        {"record_type": "receipt", "order_id": row.get("order_id"), "record_id": row.get("delivery_id")}
        for row in receipts if row.get("order_id", "").strip() not in known_ids
    ]
    return {"data_status": "SYNTHETIC DATA", "as_of_date": as_of.isoformat(),
            "orders": results, "unmatched_records_for_review": unmatched}


def main():
    parser = argparse.ArgumentParser(description="Audit synthetic purchase orders and partial deliveries")
    parser.add_argument("--as-of", default=date.today().isoformat(),
                        help="Review date in YYYY-MM-DD; defaults to today")
    args = parser.parse_args()
    as_of = parse_date(args.as_of)
    if as_of is None:
        parser.error("--as-of must be a valid YYYY-MM-DD date")
    report = audit_orders(read_csv(ROOT / "data/orders.csv"),
                          read_csv(ROOT / "data/delivery_records.csv"),
                          read_csv(ROOT / "data/receipts.csv"), as_of)
    output = ROOT / "outputs/order_audit.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in report["orders"]:
        print(f"{row['order_id']}: {row['delivery_status']}; "
              f"已到 {row['cumulative_delivered_qty']}; 未到 {row['outstanding_qty']}; "
              f"超期到货 {row['late_arrival_qty']}")
    print("Output:", output)


if __name__ == "__main__":
    main()
