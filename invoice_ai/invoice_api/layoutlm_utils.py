from transformers import LayoutLMTokenizer, LayoutLMForTokenClassification
import torch

# load pretrained model
tokenizer = LayoutLMTokenizer.from_pretrained("microsoft/layoutlm-base-uncased")
model = LayoutLMForTokenClassification.from_pretrained("microsoft/layoutlm-base-uncased")


import re

def extract_fields(words):

    text = " ".join(words)

    data = {
        "invoice_number": None,
        "date": None,
        "vendor": None,
        "amount": None
    }

    # ✅ INVOICE NUMBER (multiple formats)
    invoice_patterns = [
        r"INV[-\s]?\d+",
        r"Invoice\s*(No|#)[:\s]*([A-Za-z0-9-]+)",
        r"Bill\s*(No|#)[:\s]*([A-Za-z0-9-]+)",
        r"Ref\s*(No|#)[:\s]*([A-Za-z0-9-]+)"
    ]

    for pattern in invoice_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["invoice_number"] = match.group() if "INV" in match.group() else match.group(len(match.groups()))
            break

    # ✅ DATE (multiple formats)
    date_patterns = [
        r"\d{2}[-/]\d{2}[-/]\d{4}",
        r"\d{4}[-/]\d{2}[-/]\d{2}"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            data["date"] = match.group()
            break

    # ✅ VENDOR (multiple keywords)
    vendor_patterns = [
        r"Vendor:\s*(.*?)(Address|Invoice|Date)",
        r"Supplier:\s*(.*?)(Address|Invoice|Date)",
        r"From:\s*(.*?)(Address|Invoice|Date)"
    ]

    for pattern in vendor_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["vendor"] = match.group(1).strip()
            break

    # ✅ AMOUNT (multiple formats)
    amount_patterns = [
        r"Total Amount[:\s]*([\d,]+)",
        r"Grand Total[:\s]*([\d,]+)",
        r"Amount Due[:\s]*([\d,]+)",
        r"Total[:\s]*([\d,]+)"
    ]

    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["amount"] = match.group(1)
            break

    return data