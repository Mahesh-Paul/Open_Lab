"""
Synthetic Payment & Bank Settlement Data Generator
Simulates a high-volume payment processor ledger and acquiring bank statement.
Plants 4 intentional reconciliation gaps:
  1. In-Transit Timing Gap (Settled following month)
  2. Rounding Difference (Batch vs Per-Transaction sub-cent rounding)
  3. Duplicate Platform Entry (Webhook retry / race condition)
  4. Orphan Refund (No matching original transaction)
"""

import csv
import random
from datetime import datetime, timedelta

def generate_datasets(seed=42):
    random.seed(seed)
    
    start_date = datetime(2026, 10, 1, 8, 0, 0)
    end_date = datetime(2026, 10, 31, 23, 59, 59)
    
    platform_txs = []
    bank_settles = []
    
    # 1. Generate 250 Clean Matched Transactions
    # Each settled 1-2 days later within October
    for i in range(1, 251):
        tx_id = f"TX_202610_{i:04d}"
        created_delta = timedelta(days=random.uniform(0, 28), hours=random.uniform(0, 23), minutes=random.uniform(0, 59))
        created_at = start_date + created_delta
        
        # Amount between $5.00 and $1,500.00
        amount = round(random.uniform(5.0, 1500.0), 2)
        customer_id = f"CUST_{random.randint(1000, 9999)}"
        
        platform_txs.append({
            "transaction_id": tx_id,
            "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "PAYMENT",
            "customer_id": customer_id,
            "amount": f"{amount:.2f}",
            "currency": "USD",
            "status": "CAPTURED",
            "idempotency_key": f"idemp_{tx_id}"
        })
        
        # Bank settles funds 1-2 days later
        settle_delta = timedelta(days=random.choice([1, 2]), hours=random.uniform(1, 6))
        settled_at = created_at + settle_delta
        settle_id = f"SETTLE_202610_{i:04d}"
        
        bank_settles.append({
            "settlement_id": settle_id,
            "settled_at": settled_at.strftime("%Y-%m-%d %H:%M:%S"),
            "type": "CREDIT",
            "reference_id": tx_id,
            "amount": f"{amount:.2f}",
            "currency": "USD",
            "bank_batch_id": f"BATCH_{settled_at.strftime('%Y%m%d')}_01"
        })
        
    # =========================================================================
    # PLANT GAP 1: In-Transit Timing Gap (Settled following month: Nov 2026)
    # =========================================================================
    # A customer paid on Oct 31 at 22:45. Platform captured it in Oct.
    # Bank settles on Nov 2 (T+2 business days).
    tx_timing_id = "TX_202610_TIMING_9941"
    tx_timing_created = datetime(2026, 10, 31, 22, 45, 12)
    tx_timing_amount = 450.00
    
    platform_txs.append({
        "transaction_id": tx_timing_id,
        "created_at": tx_timing_created.strftime("%Y-%m-%d %H:%M:%S"),
        "type": "PAYMENT",
        "customer_id": "CUST_9941",
        "amount": f"{tx_timing_amount:.2f}",
        "currency": "USD",
        "status": "CAPTURED",
        "idempotency_key": f"idemp_{tx_timing_id}"
    })
    
    # Settled in November statement (Nov 2, 2026)
    settle_timing_id = "SETTLE_202611_TIMING_0012"
    settle_timing_date = datetime(2026, 11, 2, 9, 15, 0)
    bank_settles.append({
        "settlement_id": settle_timing_id,
        "settled_at": settle_timing_date.strftime("%Y-%m-%d %H:%M:%S"),
        "type": "CREDIT",
        "reference_id": tx_timing_id,
        "amount": f"{tx_timing_amount:.2f}",
        "currency": "USD",
        "bank_batch_id": "BATCH_20261102_01"
    })
    
    # =========================================================================
    # PLANT GAP 2: Rounding Difference That Only Shows When Summed
    # =========================================================================
    # 50 micro-charges. Platform computes individual amounts with fractional basis points
    # rounded to nearest cent per row.
    # The bank settles as a single aggregated batch using exact sums then rounded once,
    # resulting in a cumulative $0.14 variance across the batch.
    batch_base_date = datetime(2026, 10, 15, 10, 0, 0)
    batch_platform_sum = 0.0
    batch_exact_sum = 0.0
    
    rounding_tx_ids = []
    # Deterministic sequence producing exact rounding drift:
    for r in range(1, 51):
        r_tx_id = f"TX_202610_RND_{r:03d}"
        rounding_tx_ids.append(r_tx_id)
        # Fractional amount e.g. 19.33333
        base_val = 15.0 + (r * 0.373)
        rounded_row_val = round(base_val, 2)
        batch_platform_sum += rounded_row_val
        batch_exact_sum += base_val
        
        platform_txs.append({
            "transaction_id": r_tx_id,
            "created_at": (batch_base_date + timedelta(minutes=r*5)).strftime("%Y-%m-%d %H:%M:%S"),
            "type": "PAYMENT",
            "customer_id": f"CUST_MICRO_{r:03d}",
            "amount": f"{rounded_row_val:.2f}",
            "currency": "USD",
            "status": "CAPTURED",
            "idempotency_key": f"idemp_{r_tx_id}"
        })
        
        # Bank settles each row with its bank settlement reference
        # We plant a deliberate sub-cent cumulative drift in 14 of the rows
        # (each -0.01 on bank record) so the sum of individual rows differs by exactly $0.14
        bank_row_amount = rounded_row_val
        if r <= 14:
            bank_row_amount = round(rounded_row_val - 0.01, 2)
            
        bank_settles.append({
            "settlement_id": f"SETTLE_202610_RND_{r:03d}",
            "settled_at": (batch_base_date + timedelta(days=1, minutes=r*5)).strftime("%Y-%m-%d %H:%M:%S"),
            "type": "CREDIT",
            "reference_id": r_tx_id,
            "amount": f"{bank_row_amount:.2f}",
            "currency": "USD",
            "bank_batch_id": "BATCH_20261016_MICRO"
        })

    # =========================================================================
    # PLANT GAP 3: Duplicate Entry in One Dataset (Platform Webhook Retry)
    # =========================================================================
    # Due to a network retry / race condition, TX_202610_DUP_5021 was ingested twice
    # with identical idempotency key and amount, but different internal transaction IDs.
    dup_date = datetime(2026, 10, 20, 14, 22, 10)
    dup_amount = 320.00
    
    # Original entry:
    platform_txs.append({
        "transaction_id": "TX_202610_DUP_ORIG_5021",
        "created_at": dup_date.strftime("%Y-%m-%d %H:%M:%S"),
        "type": "PAYMENT",
        "customer_id": "CUST_5021",
        "amount": f"{dup_amount:.2f}",
        "currency": "USD",
        "status": "CAPTURED",
        "idempotency_key": "idemp_order_xyz_5021"
    })
    
    # Duplicate entry (ingested 150ms later with same idempotency key):
    platform_txs.append({
        "transaction_id": "TX_202610_DUP_GHOST_5022",
        "created_at": (dup_date + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "type": "PAYMENT",
        "customer_id": "CUST_5021",
        "amount": f"{dup_amount:.2f}",
        "currency": "USD",
        "status": "CAPTURED",
        "idempotency_key": "idemp_order_xyz_5021" # Exact duplicate key
    })
    
    # Bank only settled once for the legitimate charge
    bank_settles.append({
        "settlement_id": "SETTLE_202610_DUP_5021",
        "settled_at": (dup_date + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "type": "CREDIT",
        "reference_id": "TX_202610_DUP_ORIG_5021",
        "amount": f"{dup_amount:.2f}",
        "currency": "USD",
        "bank_batch_id": "BATCH_20261021_02"
    })
    
    # =========================================================================
    # PLANT GAP 4: Orphan Refund (No Matching Original Transaction)
    # =========================================================================
    # A refund processed on Oct 25 for a charge originating outside this ledger
    # (e.g. legacy system or direct bank chargeback debit of $180.00)
    orphan_date = datetime(2026, 10, 25, 16, 40, 0)
    orphan_amount = -180.00
    
    platform_txs.append({
        "transaction_id": "REF_202610_ORPHAN_7701",
        "created_at": orphan_date.strftime("%Y-%m-%d %H:%M:%S"),
        "type": "REFUND",
        "customer_id": "CUST_UNKNOWN_7701",
        "amount": f"{orphan_amount:.2f}",
        "currency": "USD",
        "status": "SETTLED",
        "idempotency_key": "idemp_orphan_ref_7701"
    })
    
    # Bank debits the refund
    bank_settles.append({
        "settlement_id": "SETTLE_202610_DEBIT_7701",
        "settled_at": (orphan_date + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "type": "DEBIT",
        "reference_id": "REF_202610_ORPHAN_7701",
        "amount": f"{orphan_amount:.2f}",
        "currency": "USD",
        "bank_batch_id": "BATCH_20261026_01"
    })
    
    # Sort chronologically
    platform_txs.sort(key=lambda x: x["created_at"])
    bank_settles.sort(key=lambda x: x["settled_at"])
    
    # Write to CSV
    with open("platform_transactions.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["transaction_id", "created_at", "type", "customer_id", "amount", "currency", "status", "idempotency_key"])
        writer.writeheader()
        writer.writerows(platform_txs)
        
    with open("bank_settlements.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["settlement_id", "settled_at", "type", "reference_id", "amount", "currency", "bank_batch_id"])
        writer.writeheader()
        writer.writerows(bank_settles)
        
    print(f"Generated {len(platform_txs)} platform transactions and {len(bank_settles)} bank settlement records.")
    return len(platform_txs), len(bank_settles)

if __name__ == "__main__":
    generate_datasets()

