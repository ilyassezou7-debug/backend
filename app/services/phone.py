import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

DUMMY_PATTERNS = [
    re.compile(r"^(\d)\1{7,}$"),  # e.g. 00000000, 11111111
]


def normalize_moroccan_phone(raw: str) -> str:
    """Normalize to E.164 +212XXXXXXXXX. Raises ValueError on invalid input."""
    # Arabic-Indic and Persian digits (Arabic keyboards) -> 0-9; direction marks pasted from contacts are dropped
    raw = raw.translate(_DIGITS)
    cleaned = re.sub(r"[\s\-\(\)\.\u200e\u200f]", "", raw)
    if cleaned.startswith("00212"):
        cleaned = "+" + cleaned[2:]
    if re.match(r"^[67]\d{8}$", cleaned):
        cleaned = "0" + cleaned

    if cleaned.startswith("+212"):
        normalized = cleaned
    elif cleaned.startswith("212") and len(cleaned) == 12:
        normalized = "+" + cleaned
    elif re.match(r"^0[67]\d{8}$", cleaned):
        normalized = "+212" + cleaned[1:]
    else:
        raise ValueError(f"رقم الهاتف غير صالح: {raw}")

    if not re.match(r"^\+212[67]\d{8}$", normalized):
        raise ValueError(f"يجب أن يكون الرقم مغربيا صحيحا: {raw}")

    local_part = normalized[4:]  # e.g. 6XXXXXXXX
    for pat in DUMMY_PATTERNS:
        if pat.match(local_part):
            raise ValueError("رقم الهاتف غير صالح (أرقام متكررة)")

    digits_after_prefix = local_part[1:]
    if len(set(digits_after_prefix)) == 1:
        raise ValueError("رقم الهاتف غير صالح")

    return normalized
