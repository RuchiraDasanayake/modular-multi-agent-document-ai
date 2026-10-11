"""Build the 13-document "readable but hard" benchmark pack.

Six synthetic documents with known ground truth (skewed image-only invoice PDF, faded receipt photo,
letter photo, fax-quality claim form, two-page scanned purchase order, dense digital bank statement),
four real CORD v2 validation receipts, and three FUNSD forms from datasets/funsd_pack_20.json.

Images are written to datasets/derived/hard_docs/ (gitignored); the pack to datasets/hard_docs_13.json.
Every random source is seeded, so rebuilding with the same fonts and library versions gives the same images.

Usage:
  python scripts/build_hard_docs_pack.py
  python scripts/build_hard_docs_pack.py --font-dir /usr/share/fonts/msttcorefonts
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
from pathlib import Path

import fitz  # PyMuPDF, used only to build the digital (text-layer) PDF
import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "datasets" / "derived" / "hard_docs"
PACK_PATH = REPO_ROOT / "datasets" / "hard_docs_13.json"
CORD_VALIDATION_GLOB = "validation-*.parquet"
CORD_INDICES = [3, 17, 42, 66]
FUNSD_CASES = ["funsd_82250337_0338", "funsd_82092117", "funsd_82200067_0069"]
REQUIRED_FONTS = ["arial.ttf", "arialbd.ttf", "consola.ttf", "times.ttf", "timesbd.ttf", "cour.ttf", "segoepr.ttf"]

FIELD_DESCRIPTIONS = {
    "invoice_number": "The invoice number / invoice ID.",
    "invoice_date": "The invoice issue date, as written.",
    "vendor_name": "The company that issued the invoice.",
    "subtotal_amount": "Subtotal before tax. Number only.",
    "tax_amount": "Tax / VAT amount. Number only.",
    "total_amount": "Final total amount due. Number only.",
    "cash_amount": "Cash paid by the customer. Number only.",
    "change_amount": "Change returned to the customer. Number only.",
    "document_date": "The date printed on the document.",
    "sender": "The person who signed or sent the letter.",
    "recipient": "The person the letter is addressed to.",
    "date": "The date of the letter, as written.",
    "subject": "The subject line of the letter.",
    "claim_reference": "The claim reference number.",
    "policy_number": "The insurance policy number.",
    "claimant_name": "The full name of the claimant.",
    "incident_date": "The date of the incident.",
    "claim_amount": "The amount claimed. Number only.",
    "po_number": "The purchase order number.",
    "order_date": "The order date.",
    "supplier_name": "The supplier company name.",
    "account_holder": "The account holder's name.",
    "account_number": "The bank account number.",
    "statement_date": "The date the statement was issued.",
    "opening_balance": "Opening balance for the period. Number only.",
    "closing_balance": "Closing balance for the period. Number only.",
}


class Builder:
    def __init__(self, font_dir: Path, out_dir: Path) -> None:
        self.font_dir = font_dir
        self.out_dir = out_dir
        self.rng = random.Random(7)
        self.np_rng = np.random.default_rng(7)

    def font(self, name: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(self.font_dir / name), size)

    @staticmethod
    def page(w: int = 1240, h: int = 1754, color: int = 255) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("L", (w, h), color)
        return img, ImageDraw.Draw(img)

    def add_noise(self, img: Image.Image, sigma: float) -> Image.Image:
        arr = np.asarray(img).astype(np.float32)
        arr += self.np_rng.normal(0, sigma, arr.shape)
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    def salt_pepper(self, img: Image.Image, amount: float) -> Image.Image:
        arr = np.asarray(img).copy()
        mask = self.np_rng.random(arr.shape)
        arr[mask < amount / 2] = 0
        arr[mask > 1 - amount / 2] = 255
        return Image.fromarray(arr)

    @staticmethod
    def gradient_shadow(img: Image.Image, strength: float) -> Image.Image:
        w, h = img.size
        xs = np.linspace(0, 1, w)[None, :]
        ys = np.linspace(0, 1, h)[:, None]
        shade = 1.0 - strength * (0.6 * xs + 0.4 * ys)
        arr = np.asarray(img).astype(np.float32) * shade
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    @staticmethod
    def low_contrast(img: Image.Image, lo: int, hi: int) -> Image.Image:
        arr = np.asarray(img).astype(np.float32) / 255.0
        return Image.fromarray((lo + arr * (hi - lo)).astype(np.uint8))

    @staticmethod
    def jpeg_roundtrip(img: Image.Image, quality: int) -> Image.Image:
        buffer = io.BytesIO()
        img.convert("RGB").save(buffer, format="JPEG", quality=quality)
        buffer.seek(0)
        out = Image.open(buffer).convert("L")
        out.load()
        return out

    def invoice_scanned(self) -> dict:
        """Skewed, noisy, image-only invoice PDF (no text layer)."""
        img, d = self.page()
        f = self.font
        d.text((90, 90), "NORTHWIND OFFICE SUPPLIES (PVT) LTD", font=f("arialbd.ttf", 40), fill=20)
        d.text((90, 145), "No. 42, Galle Road, Colombo 03  |  Tel: +94 11 255 7788", font=f("arial.ttf", 24), fill=40)
        d.text((820, 230), "TAX INVOICE", font=f("arialbd.ttf", 44), fill=10)
        d.text((90, 320), "Invoice No:  INV-2024-0871", font=f("arial.ttf", 30), fill=20)
        d.text((90, 365), "Invoice Date:  14/03/2024", font=f("arial.ttf", 30), fill=20)
        d.text((90, 410), "Due Date:  13/04/2024", font=f("arial.ttf", 30), fill=20)
        d.text((700, 320), "Bill To:", font=f("arialbd.ttf", 30), fill=20)
        d.text((700, 365), "Lakeside Medical Centre", font=f("arial.ttf", 30), fill=20)
        d.text((700, 410), "Kandy, Sri Lanka", font=f("arial.ttf", 30), fill=20)
        y = 520
        d.line((90, y, 1150, y), fill=0, width=3)
        for col, x in (("Description", 100), ("Qty", 700), ("Unit Price", 820), ("Amount", 1010)):
            d.text((x, y + 12), col, font=f("arialbd.ttf", 28), fill=10)
        y += 60
        d.line((90, y, 1150, y), fill=0, width=2)
        items = [
            ("A4 Copy Paper (box)", 12, "2,450.00", "29,400.00"),
            ("Toner Cartridge HP 85A", 3, "8,900.00", "26,700.00"),
            ("Ring Binders", 40, "185.00", "7,400.00"),
            ("Whiteboard Markers (set)", 6, "650.00", "3,900.00"),
        ]
        for desc, qty, unit, amt in items:
            y += 18
            d.text((100, y), desc, font=f("arial.ttf", 28), fill=25)
            d.text((710, y), str(qty), font=f("arial.ttf", 28), fill=25)
            d.text((820, y), unit, font=f("arial.ttf", 28), fill=25)
            d.text((1010, y), amt, font=f("arial.ttf", 28), fill=25)
            y += 40
        y += 30
        d.line((640, y, 1150, y), fill=0, width=2)
        for label, val in (("Subtotal", "67,400.00"), ("VAT 18%", "12,132.00"), ("TOTAL DUE (LKR)", "79,532.00")):
            y += 20
            bold = label.startswith("TOTAL")
            d.text((660, y), label, font=f("arialbd.ttf" if bold else "arial.ttf", 30), fill=10)
            d.text((1000, y), val, font=f("arialbd.ttf" if bold else "arial.ttf", 30), fill=10)
            y += 45
        d.text(
            (90, 1600),
            "Payment: Bank transfer to Commercial Bank A/C 8001234567. Thank you for your business.",
            font=f("arial.ttf", 22),
            fill=60,
        )
        img = img.rotate(3.2, resample=Image.BICUBIC, expand=False, fillcolor=235)
        img = img.filter(ImageFilter.GaussianBlur(1.1))
        img = self.jpeg_roundtrip(self.add_noise(img, 14), 35)
        path = self.out_dir / "hard_invoice_scanned_skewed.pdf"
        img.convert("RGB").save(path, "PDF", resolution=150)
        return {
            "case_id": "hard_invoice_scanned_skewed",
            "tags": ["scanned", "noisy_ocr", "table", "invoice", "pdf_image_only"],
            "path": path,
            "expected": {
                "invoice_number": "INV-2024-0871",
                "invoice_date": "14/03/2024",
                "vendor_name": "NORTHWIND OFFICE SUPPLIES (PVT) LTD",
                "subtotal_amount": "67,400.00",
                "tax_amount": "12,132.00",
                "total_amount": "79,532.00",
            },
        }

    def receipt_faded(self) -> dict:
        """Faded thermal receipt photo with shading."""
        img, d = self.page(620, 1300, 250)
        mono = self.font("consola.ttf", 26)
        lines = [
            "      CAFE MOUNT LAVINIA", "   45 Hotel Rd, Mt Lavinia", "      Tel 011 271 1711", "",
            "Date: 02/11/2023   Time: 19:42", "Bill#: 004519     Table: 07", "-" * 34,
            "2 x Iced Coffee         1,300.00", "1 x Chicken Kottu       1,450.00", "1 x Veg Fried Rice      1,150.00",
            "3 x Lime Juice            900.00", "-" * 34, "SUBTOTAL                4,800.00", "SERVICE CHG 10%           480.00",
            "TOTAL                   5,280.00", "CASH                    6,000.00", "CHANGE                    720.00", "-" * 34,
            "   THANK YOU - COME AGAIN",
        ]
        y = 40
        for line in lines:
            d.text((30, y), line, font=mono, fill=30)
            y += 44
        img = self.gradient_shadow(self.low_contrast(img, 95, 215), 0.35)
        img = img.rotate(-2.0, resample=Image.BICUBIC, expand=True, fillcolor=120)
        img = self.add_noise(img.filter(ImageFilter.GaussianBlur(0.9)), 10)
        path = self.out_dir / "hard_receipt_faded_photo.jpg"
        img.convert("RGB").save(path, quality=55)
        return {
            "case_id": "hard_receipt_faded_photo",
            "tags": ["receipt", "noisy_ocr", "scanned", "low_contrast"],
            "path": path,
            "expected": {
                "total_amount": "5,280.00",
                "subtotal_amount": "4,800.00",
                "cash_amount": "6,000.00",
                "change_amount": "720.00",
                "document_date": "02/11/2023",
            },
        }

    def letter_photo(self) -> dict:
        """Business letter photo: shadow gradient, slight skew, serif font."""
        img, d = self.page()
        serif = self.font("times.ttf", 30)
        serif_bold = self.font("timesbd.ttf", 34)
        d.text((90, 90), "Ceylon Tea Exporters Association", font=serif_bold, fill=15)
        d.text((90, 140), "12 Duke Street, Colombo 01", font=serif, fill=30)
        d.text((90, 260), "18 September 2023", font=serif, fill=20)
        d.text((90, 340), "Ms. Anjali Perera", font=serif, fill=20)
        d.text((90, 380), "Procurement Manager, Harbour Logistics Ltd", font=serif, fill=20)
        d.text((90, 420), "Port City, Colombo", font=serif, fill=20)
        d.text((90, 510), "Subject: Revised shipping schedule for Q4 consignments", font=serif_bold, fill=15)
        body = [
            "Dear Ms. Perera,", "",
            "Further to our meeting on 11 September, we write to confirm that the",
            "October and November consignments will now depart on the 5th and 19th",
            "of each month respectively. The revised schedule reflects the new berth",
            "allocation at the South Container Terminal.", "",
            "Please let us know by 30 September 2023 if these dates are suitable.", "",
            "Yours sincerely,", "", "", "Rohan Wickramasinghe", "Secretary General",
        ]
        y = 590
        for line in body:
            d.text((90, y), line, font=serif, fill=25)
            y += 44
        img = self.gradient_shadow(img, 0.45)
        img = img.rotate(-1.6, resample=Image.BICUBIC, expand=True, fillcolor=90)
        img = self.add_noise(img.filter(ImageFilter.GaussianBlur(1.3)), 9)
        path = self.out_dir / "hard_letter_photo.jpg"
        img.convert("RGB").save(path, quality=60)
        return {
            "case_id": "hard_letter_photo",
            "tags": ["text", "correspondence", "scanned", "photo"],
            "path": path,
            "expected": {
                "sender": "Rohan Wickramasinghe",
                "recipient": "Anjali Perera",
                "date": "18 September 2023",
                "subject": "Revised shipping schedule for Q4 consignments",
            },
        }

    def fax_form(self) -> dict:
        """Fax-quality claim form: binarized, low resolution, speckle noise, handwriting-like values."""
        img, d = self.page()
        d.text((380, 80), "INSURANCE CLAIM FORM", font=self.font("arialbd.ttf", 46), fill=0)
        d.text((90, 150), "FAX: +94 11 230 4455        Page 1 of 1", font=self.font("cour.ttf", 26), fill=0)
        rows = [
            ("Claim Reference No.", "CLM-77310-B"), ("Policy Number", "POL-5520918"),
            ("Claimant Name", "Dilan Jayawardena"), ("Date of Incident", "07/06/2024"),
            ("Contact Phone", "077 412 9035"), ("Claim Amount (LKR)", "145,750.00"),
        ]
        y = 260
        for label, value in rows:
            d.rectangle((90, y, 1150, y + 80), outline=0, width=2)
            d.line((520, y, 520, y + 80), fill=0, width=2)
            d.text((105, y + 22), label, font=self.font("arial.ttf", 30), fill=0)
            d.text((540, y + 18), value, font=self.font("segoepr.ttf", 36), fill=0)
            y += 80
        d.text((90, y + 60), "Signature: ____________________     Date: ______________", font=self.font("arial.ttf", 28), fill=0)
        small = img.resize((620, 877), Image.BILINEAR).point(lambda p: 0 if p < 150 else 255)
        small = self.salt_pepper(small, 0.03)
        img = small.resize((1240, 1754), Image.NEAREST).rotate(0.8, fillcolor=255)
        path = self.out_dir / "hard_fax_claim_form.png"
        img.save(path)
        return {
            "case_id": "hard_fax_claim_form",
            "tags": ["form", "scanned", "noisy_ocr", "fax", "handwriting_like"],
            "path": path,
            "expected": {
                "claim_reference": "CLM-77310-B",
                "policy_number": "POL-5520918",
                "claimant_name": "Dilan Jayawardena",
                "incident_date": "07/06/2024",
                "claim_amount": "145,750.00",
            },
        }

    def multipage_scanned(self) -> dict:
        """Two-page scanned PDF: identifiers on page 1, totals only on page 2."""
        p1, d1 = self.page()
        d1.text((90, 90), "PURCHASE ORDER", font=self.font("arialbd.ttf", 48), fill=10)
        d1.text((90, 180), "PO Number: PO-55120", font=self.font("arial.ttf", 32), fill=20)
        d1.text((90, 230), "Order Date: 2024-01-22", font=self.font("arial.ttf", 32), fill=20)
        d1.text((90, 280), "Supplier: Lanka Hardware Traders", font=self.font("arial.ttf", 32), fill=20)
        y = 380
        for i in range(1, 19):
            line = f"{i:02d}  Item code HW-{1000 + i}   qty {self.rng.randint(1, 30):>3}   unit {self.rng.randint(150, 9000):>6}.00"
            d1.text((90, y), line, font=self.font("cour.ttf", 26), fill=30)
            y += 52
        d1.text((90, 1650), "continued on next page ...", font=self.font("arial.ttf", 24), fill=60)
        p2, d2 = self.page()
        d2.text((90, 90), "PO-55120  (page 2 of 2)", font=self.font("arial.ttf", 28), fill=40)
        d2.text((640, 300), "Net Total:     412,880.00", font=self.font("arial.ttf", 34), fill=15)
        d2.text((640, 360), "VAT (18%):      74,318.40", font=self.font("arial.ttf", 34), fill=15)
        d2.text((640, 420), "GRAND TOTAL:   487,198.40", font=self.font("arialbd.ttf", 36), fill=5)
        d2.text((90, 600), "Authorised by: K. Fernando, Head of Procurement", font=self.font("arial.ttf", 30), fill=25)
        pages = []
        for im, angle in ((p1, 1.4), (p2, -2.1)):
            im = im.rotate(angle, resample=Image.BICUBIC, fillcolor=230).filter(ImageFilter.GaussianBlur(1.0))
            pages.append(self.jpeg_roundtrip(self.add_noise(im, 12), 40).convert("RGB"))
        path = self.out_dir / "hard_multipage_po_scanned.pdf"
        pages[0].save(path, "PDF", resolution=150, save_all=True, append_images=pages[1:])
        return {
            "case_id": "hard_multipage_po_scanned",
            "tags": ["scanned", "multi_page", "table", "pdf_image_only"],
            "path": path,
            "expected": {
                "po_number": "PO-55120",
                "order_date": "2024-01-22",
                "supplier_name": "Lanka Hardware Traders",
                "tax_amount": "74,318.40",
                "total_amount": "487,198.40",
            },
        }

    def bank_statement_digital(self) -> dict:
        """Dense digital bank statement (text layer) with many competing amounts."""
        path = self.out_dir / "hard_bank_statement_digital.pdf"
        doc = fitz.open()
        pg = doc.new_page(width=595, height=842)
        y = 50

        def put(x: float, text: str, size: float = 9, bold: bool = False) -> None:
            pg.insert_text((x, y), text, fontsize=size, fontname="hebo" if bold else "helv")

        balance = 182450.75
        tx_rng = random.Random(3)
        rows = []
        for day in range(2, 31, 2):
            if tx_rng.random() < 0.7:
                amount = round(tx_rng.uniform(1500, 25000), 2)
                balance = round(balance - amount, 2)
                merchant = tx_rng.choice(["POS Keells Super", "ATM Withdrawal", "CEB Bill Payment", "Dialog Axiata", "Fuel - Lanka IOC"])
                rows.append((f"{day:02d}/08/2024", merchant, f"{amount:,.2f}", "", f"{balance:,.2f}"))
            else:
                amount = round(tx_rng.uniform(5000, 40000), 2)
                balance = round(balance + amount, 2)
                rows.append((f"{day:02d}/08/2024", "Inward Transfer", "", f"{amount:,.2f}", f"{balance:,.2f}"))
        closing = f"{balance:,.2f}"
        put(40, "SEYLAN BANK PLC - ACCOUNT STATEMENT", 14, True)
        y += 22
        put(40, "Account Holder: Nimal Senanayake")
        put(330, "Account No: 0045-2231-7789")
        y += 14
        put(40, "Statement Period: 01/08/2024 - 31/08/2024")
        put(330, "Statement Date: 02/09/2024")
        y += 14
        put(40, "Opening Balance: 182,450.75")
        put(330, f"Closing Balance: {closing}", 9, True)
        y += 24
        for x, heading in ((40, "Date"), (100, "Description"), (330, "Debit"), (410, "Credit"), (490, "Balance")):
            put(x, heading, 9, True)
        y += 14
        for row in rows:
            for x, text in zip((40, 100, 330, 410, 490), row):
                put(x, text)
            y += 13
        doc.save(path)
        doc.close()
        return {
            "case_id": "hard_bank_statement_digital",
            "tags": ["table", "text", "digital_pdf", "dense_numbers"],
            "path": path,
            "expected": {
                "account_holder": "Nimal Senanayake",
                "account_number": "0045-2231-7789",
                "statement_date": "02/09/2024",
                "opening_balance": "182,450.75",
                "closing_balance": closing,
            },
        }

    def synthetic_cases(self) -> list[dict]:
        cases = [
            self.invoice_scanned(),
            self.receipt_faded(),
            self.letter_photo(),
            self.fax_form(),
            self.multipage_scanned(),
            self.bank_statement_digital(),
        ]
        return [
            {
                "case_id": case["case_id"],
                "tags": case["tags"],
                "path": _repo_relative(case["path"]),
                "fields": {key: FIELD_DESCRIPTIONS[key] for key in case["expected"]},
                "expected": case["expected"],
            }
            for case in cases
        ]

    def cord_cases(self, cord_root: Path) -> list[dict]:
        files = sorted((cord_root / "data").glob(CORD_VALIDATION_GLOB))
        if not files:
            raise SystemExit(f"No CORD v2 validation parquet under {cord_root / 'data'} (see docs/REPRODUCING_RESULTS.md)")
        rows: list[dict] = []
        for file in files:
            rows.extend(pq.read_table(file).to_pylist())
        cases = []
        for index in CORD_INDICES:
            row = rows[index]
            expected = _cord_expected_fields(row["ground_truth"])
            if not expected:
                continue
            path = self.out_dir / f"cord_validation_{index:04d}.jpg"
            Image.open(io.BytesIO(row["image"]["bytes"])).convert("RGB").save(path, quality=92)
            cases.append(
                {
                    "case_id": f"cord_validation_{index:04d}",
                    "tags": ["receipt", "scanned", "noisy_ocr", "real_cord"],
                    "path": _repo_relative(path),
                    "fields": {key: "Number only." for key in expected},
                    "expected": expected,
                }
            )
        return cases


def _cord_expected_fields(ground_truth: str) -> dict[str, str]:
    gt = json.loads(ground_truth).get("gt_parse", {})
    total = gt.get("total", {}) if isinstance(gt.get("total"), dict) else {}
    sub = gt.get("sub_total", {}) if isinstance(gt.get("sub_total"), dict) else {}
    pairs = {
        "total_amount": total.get("total_price"),
        "cash_amount": total.get("cashprice"),
        "change_amount": total.get("changeprice"),
        "subtotal_amount": sub.get("subtotal_price"),
        "tax_amount": sub.get("tax_price"),
    }
    return {key: str(value).strip() for key, value in pairs.items() if isinstance(value, str) and value.strip()}


def _funsd_cases() -> list[dict]:
    funsd = json.loads((REPO_ROOT / "datasets" / "funsd_pack_20.json").read_text(encoding="utf-8"))
    return [case for case in funsd["cases"] if case["case_id"] in FUNSD_CASES]


def _repo_relative(path: Path) -> str:
    return str(Path(path).resolve().relative_to(REPO_ROOT)).replace("\\", "/")


def _default_font_dir() -> Path | None:
    windows_dir = os.environ.get("WINDIR")
    return Path(windows_dir) / "Fonts" if windows_dir else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--font-dir", type=Path, default=_default_font_dir(), help="Folder containing the Microsoft core fonts.")
    parser.add_argument("--cord-root", type=Path, default=REPO_ROOT / "datasets" / "external" / "cord-v2")
    args = parser.parse_args()
    if args.font_dir is None:
        raise SystemExit("Pass --font-dir pointing at a folder with: " + ", ".join(REQUIRED_FONTS))
    missing = [name for name in REQUIRED_FONTS if not (args.font_dir / name).exists()]
    if missing:
        raise SystemExit(f"Missing fonts in {args.font_dir}: {', '.join(missing)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    builder = Builder(args.font_dir, OUT_DIR)
    cases = builder.synthetic_cases() + builder.cord_cases(args.cord_root) + _funsd_cases()
    pack = {
        "name": "hard_mixed_13",
        "description": (
            "Readable-but-hard documents: 6 synthetic (skew, blur, noise, fax, faded, multi-page, dense digital), "
            "4 real CORD v2 receipts, 3 FUNSD forms. Built by scripts/build_hard_docs_pack.py."
        ),
        "batch_mode": "per_case",
        "cases": cases,
    }
    PACK_PATH.write_text(json.dumps(pack, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {_repo_relative(PACK_PATH)}; images in {_repo_relative(OUT_DIR)}")


if __name__ == "__main__":
    main()
