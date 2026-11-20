import zipfile
import os

files_to_zip = [
    "data_generator.py",
    "recon_engine.py",
    "test_recon.py",
    "export_recon_json.py",
    "index.html",
    "package.json",
    "vercel.json",
    "platform_transactions.csv",
    "bank_settlements.csv",
    "recon_data.json",
    "README.md",
    "SUBMISSION.md"
]

zip_filename = "onelab_payments_reconciliation.zip"

with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
    for f in files_to_zip:
        if os.path.exists(f):
            zipf.write(f, arcname=f)
            print(f"Added: {f}")

print(f"Successfully created {zip_filename} ({os.path.getsize(zip_filename)} bytes)")

