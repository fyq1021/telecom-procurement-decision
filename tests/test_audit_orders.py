"""Business checks for the synthetic partial-delivery audit."""

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from audit_orders import audit_orders, read_csv  # noqa: E402


class OrderAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orders = read_csv(ROOT / "data/orders.csv")
        cls.deliveries = read_csv(ROOT / "data/delivery_records.csv")
        cls.receipts = read_csv(ROOT / "data/receipts.csv")
        cls.report = audit_orders(cls.orders, cls.deliveries, cls.receipts, date(2026, 10, 13))
        cls.by_id = {row["order_id"]: row for row in cls.report["orders"]}

    def test_normal_split_delivery_and_completion_date(self):
        row = self.by_id["O-1001"]
        self.assertEqual(row["delivery_status"], "全部完成")
        self.assertTrue(row["normal_split_delivery"])
        self.assertEqual((row["cumulative_delivered_qty"], row["outstanding_qty"]), (100, 0))
        self.assertEqual(row["final_delivery_date"], "2026-09-18")
        self.assertEqual((row["late_arrival_qty"], row["overdue_days"]), (0, 0))

    def test_partial_before_due_has_no_completion_date(self):
        row = self.by_id["O-1002"]
        self.assertEqual(row["delivery_status"], "部分交付未逾期")
        self.assertEqual(row["outstanding_qty"], 50)
        self.assertIsNone(row["final_delivery_date"])
        self.assertEqual(row["receipt_check"], "待核查")

    def test_partial_after_due_counts_late_arrivals_and_running_overdue(self):
        row = self.by_id["O-1003"]
        self.assertEqual(row["delivery_status"], "部分交付已逾期")
        self.assertEqual((row["cumulative_delivered_qty"], row["outstanding_qty"]), (30, 20))
        self.assertEqual(row["late_arrival_qty"], 10)
        self.assertEqual(row["overdue_days"], 8)
        self.assertIsNone(row["final_delivery_date"])
        self.assertEqual(row["receipt_check"], "数量或订单不一致")

    def test_completed_late_uses_actual_completion_date(self):
        row = self.by_id["O-1004"]
        self.assertEqual(row["delivery_status"], "全部完成")
        self.assertEqual(row["final_delivery_date"], "2026-10-04")
        self.assertEqual((row["late_arrival_qty"], row["overdue_days"]), (40, 3))

    def test_excess_and_contract_mismatch_remain_visible(self):
        row = self.by_id["O-1005"]
        self.assertEqual(row["delivery_status"], "超量交付")
        self.assertEqual((row["cumulative_delivered_qty"], row["outstanding_qty"], row["excess_qty"]), (35, 0, 5))
        self.assertEqual(row["contract_amount_check"], "金额不一致")

    def test_no_delivery_does_not_invent_completion(self):
        row = self.by_id["O-1006"]
        self.assertEqual(row["delivery_status"], "未到货已逾期")
        self.assertEqual(row["outstanding_qty"], 20)
        self.assertEqual(row["overdue_days"], 12)
        self.assertIsNone(row["final_delivery_date"])
        self.assertEqual(row["documents_check"], "待补件")

    def test_missing_due_date_is_for_review(self):
        row = self.by_id["O-1007"]
        self.assertEqual(row["delivery_status"], "待核查")
        self.assertIsNone(row["late_arrival_qty"])
        self.assertIsNone(row["overdue_days"])
        self.assertIsNone(row["final_delivery_date"])
        self.assertEqual(row["documents_check"], "待核查")

    def test_missing_due_date_does_not_erase_known_completion_date(self):
        orders = [dict(row) for row in self.orders]
        next(row for row in orders if row["order_id"] == "O-1001")["due_date"] = ""
        report = audit_orders(orders, self.deliveries, self.receipts, date(2026, 10, 13))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1001")
        self.assertEqual(row["delivery_status"], "待核查")
        self.assertEqual(row["final_delivery_date"], "2026-09-18")
        self.assertIsNone(row["overdue_days"])

    def test_unknown_order_and_future_arrival_are_not_silently_accepted(self):
        deliveries = self.deliveries + [
            {"delivery_id": "DL-X", "order_id": "UNKNOWN", "arrival_date": "2026-10-10", "quantity": "3"},
            {"delivery_id": "DL-F", "order_id": "O-1002", "arrival_date": "2026-10-30", "quantity": "50"},
        ]
        report = audit_orders(self.orders, deliveries, self.receipts, date(2026, 10, 13))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1002")
        self.assertEqual(row["delivery_status"], "部分交付未逾期")
        self.assertEqual(row["cumulative_delivered_qty"], 30)
        self.assertIsNone(row["final_delivery_date"])
        self.assertEqual(row["future_delivery_records_excluded"], 1)
        self.assertTrue(row["warnings"])
        self.assertEqual(row["receipt_check"], "待核查")  # DL-003 is missing its signed receipt.
        self.assertEqual(report["unmatched_records_for_review"][0]["order_id"], "UNKNOWN")

    def test_historical_review_ignores_future_batch_and_its_receipt(self):
        report = audit_orders(self.orders, self.deliveries, self.receipts, date(2026, 9, 16))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1001")
        self.assertEqual(row["cumulative_delivered_qty"], 60)
        self.assertEqual(row["outstanding_qty"], 40)
        self.assertEqual(row["receipt_check"], "一致")
        self.assertIsNone(row["final_delivery_date"])

    def test_invalid_batch_does_not_report_a_false_total(self):
        deliveries = self.deliveries + [
            {"delivery_id": "DL-BAD", "order_id": "O-1001", "arrival_date": "2026-09-19", "quantity": "?"}
        ]
        report = audit_orders(self.orders, deliveries, self.receipts, date(2026, 10, 13))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1001")
        self.assertEqual(row["delivery_status"], "待核查")
        self.assertIsNone(row["cumulative_delivered_qty"])
        self.assertIsNone(row["outstanding_qty"])
        self.assertIsNone(row["final_delivery_date"])

    def test_duplicate_batch_id_across_orders_marks_both_for_review(self):
        deliveries = self.deliveries + [
            {"delivery_id": "DL-001", "order_id": "O-1002", "arrival_date": "2026-10-11", "quantity": "5"}
        ]
        report = audit_orders(self.orders, deliveries, self.receipts, date(2026, 10, 13))
        by_id = {row["order_id"]: row for row in report["orders"]}
        for order_id in ("O-1001", "O-1002"):
            self.assertEqual(by_id[order_id]["delivery_status"], "待核查")
            self.assertIsNone(by_id[order_id]["cumulative_delivered_qty"])

    def test_invalid_order_quantity_cannot_pass_contract_check(self):
        orders = [dict(row) for row in self.orders]
        next(row for row in orders if row["order_id"] == "O-1001")["order_qty"] = "0"
        next(row for row in orders if row["order_id"] == "O-1001")["contract_amount"] = "0"
        report = audit_orders(orders, self.deliveries, self.receipts, date(2026, 10, 13))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1001")
        self.assertEqual(row["contract_amount_check"], "待核查")

    def test_extra_receipt_without_matching_batch_is_flagged(self):
        receipts = self.receipts + [
            {"delivery_id": "DL-NOT-REAL", "order_id": "O-1001", "signed_quantity": "5", "receipt_file_present": "Y"}
        ]
        report = audit_orders(self.orders, self.deliveries, receipts, date(2026, 10, 13))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1001")
        self.assertEqual(row["receipt_check"], "数量或订单不一致")

    def test_on_due_date_partial_order_is_not_yet_overdue(self):
        report = audit_orders(self.orders, self.deliveries, self.receipts, date(2026, 10, 20))
        row = next(item for item in report["orders"] if item["order_id"] == "O-1002")
        self.assertEqual(row["delivery_status"], "部分交付未逾期")
        self.assertEqual(row["overdue_days"], 0)


if __name__ == "__main__":
    unittest.main()
