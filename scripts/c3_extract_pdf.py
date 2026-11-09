"""C-3: Extract PDF text and match percentages for the 4 verification JDs."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf
from pathlib import Path

ARTIFACTS = Path("data/artifacts")

PDFS = {
    "AI Engineer": ARTIFACTS / "Pallav_Anand_Lead_AI_Backend_Engineer_Final_Verification_Co.pdf",
    "Gurugram GenAI": ARTIFACTS / "Pallav_Anand_Senior_AI_Platform_Engineer_Verification_Co.pdf",
    "DevOps/Cloud": ARTIFACTS / "Pallav_Anand_Registered_Nurse_Gap_Verification_Co.pdf",
    "No title/company": ARTIFACTS / "Pallav_Anand_Applied_AI_Engineer_Confidential.pdf",
}

for label, path in PDFS.items():
    if not path.exists():
        print(f"\n[{label}] NOT FOUND: {path}")
        continue
    doc = pymupdf.open(str(path))
    text = "".join(page.get_text() for page in doc)
    print(f"\n{'='*60}")
    print(f"[{label}] {path.name}")
    print(f"Pages: {len(doc)}  Chars: {len(text)}")
    print("--- First 800 chars ---")
    print(text[:800])
    print("--- Last 400 chars ---")
    print(text[-400:])
