"""
Comprehensive Automated Test Suite for Payment Reconciliation Engine
Verifies all 4 planted gaps, accounting balances, and edge cases.
"""

import unittest
from recon_engine import ReconciliationEngine, to_cents, from_cents

class TestPaymentReconciliation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = ReconciliationEngine("platform_transactions.csv", "bank_settlements.csv", month_str="2026-10")
        cls.metrics = cls.engine.reconcile()

    def test_datasets_loaded_correctly(self):
        """Verify both datasets are populated with expected row counts."""
        self.assertGreater(self.metrics["total_platform_records"], 250)
        self.assertGreater(self.metrics["total_bank_records"], 250)

    def test_gap1_timing_gap_detected(self):
        """Verify the October transaction settled in November is correctly identified."""
        timing_gaps = self.engine.timing_gaps
        self.assertEqual(len(timing_gaps), 1, "Exactly one in-transit timing transaction expected.")
        
        tx = timing_gaps[0]
        self.assertEqual(tx["platform_tx_id"], "TX_202610_TIMING_9941")
        self.assertEqual(tx["amount"], "450.00")
        self.assertEqual(tx["amount_cents"], 45000)
        self.assertTrue(tx["settled_at"].startswith("2026-11"), "Must settle in November.")
        self.assertGreater(tx["delay_hours"], 24.0, "Must reflect T+1/T+2 settlement delay.")

    def test_gap2_rounding_difference_detected(self):
        """Verify the cumulative rounding variance is identified across rows."""
        rounding_gaps = self.engine.rounding_gaps
        self.assertEqual(len(rounding_gaps), 14, "Expected 14 rows with 1-cent rounding variances.")
        
        total_rounding_variance = self.metrics["cumulative_rounding_variance_cents"]
        self.assertEqual(total_rounding_variance, -14, "Cumulative rounding variance must equal exactly -14 cents (-$0.14).")
        self.assertEqual(self.metrics["cumulative_rounding_variance"], "-0.14")

    def test_gap3_duplicate_platform_entry_detected(self):
        """Verify duplicate platform entry from webhook idempotency collision is isolated."""
        duplicates = self.engine.duplicate_platform_entries
        self.assertEqual(len(duplicates), 1, "Exactly one duplicate platform entry expected.")
        
        dup = duplicates[0]
        self.assertEqual(dup["duplicate_transaction_id"], "TX_202610_DUP_GHOST_5022")
        self.assertEqual(dup["original_transaction_id"], "TX_202610_DUP_ORIG_5021")
        self.assertEqual(dup["amount"], "320.00")
        self.assertEqual(dup["amount_cents"], 32000)
        self.assertEqual(dup["idempotency_key"], "idemp_order_xyz_5021")

    def test_gap4_orphan_refund_detected(self):
        """Verify orphan refund without matching original payment is flagged."""
        orphans = self.engine.orphan_refunds
        self.assertEqual(len(orphans), 1, "Expected exactly 1 orphan refund.")
        
        ref = orphans[0]
        self.assertEqual(ref["refund_id"], "REF_202610_ORPHAN_7701")
        self.assertEqual(ref["amount"], "-180.00")
        self.assertEqual(ref["amount_cents"], -18000)
        self.assertEqual(ref["status"], "ORPHAN_REFUND")

    def test_exact_balance_sheet_closure(self):
        """
        Verify the fundamental reconciliation equation:
        Platform_Gross - Timing_Gaps - Duplicate_Ghosts + Cumulative_Rounding == Bank_October_Actual
        NET UNEXPLAINED VARIANCE MUST EQUAL EXACTLY ZERO.
        """
        m = self.metrics
        platform_gross = m["platform_raw_total_cents"]
        bank_actual = m["bank_october_total_cents"]
        timing = m["timing_gap_cents"]
        dups = m["duplicate_entry_cents"]
        rounding = m["cumulative_rounding_variance_cents"]
        
        calculated_bank = platform_gross - timing - dups + rounding
        self.assertEqual(calculated_bank, bank_actual, "Adjusted Platform total + Rounding must exactly match Bank actual.")
        self.assertEqual(m["net_unreconciled_variance_cents"], 0, "Net unexplained variance must be 0 cents.")
        self.assertTrue(m["is_fully_reconciled"], "Reconciliation status must be True.")

if __name__ == "__main__":
    unittest.main()

