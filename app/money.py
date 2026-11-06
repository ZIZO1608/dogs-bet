from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def fmt_usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def fmt_syp(amount: int) -> str:
    return f"{amount:,} SYP"


def usd_cents_to_syp(cents: int, rate: float) -> int:
    return int((Decimal(cents) / 100 * Decimal(str(rate))).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def syp_to_usd_cents(syp: int, rate: float) -> int:
    if rate <= 0:
        raise ValueError("SYP rate must be positive")
    return int((Decimal(syp) / Decimal(str(rate)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_cents(amount: int, currency: str, syp_rate: float) -> int:
    """Convert an amount in whole units of `currency` into USD cents."""
    if currency == "SYP":
        return syp_to_usd_cents(amount, syp_rate)
    return amount * 100


def parse_usd_to_cents(text: str) -> int | None:
    """'12', '12.5', '12,50', '$12.50' -> cents. Returns None if invalid or not positive."""
    cleaned = text.strip().replace("$", "").replace(",", ".").replace(" ", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value <= 0 or value.as_tuple().exponent < -2:
        return None
    return int(value * 100)


def parse_positive_int(text: str) -> int | None:
    cleaned = text.strip().replace(",", "").replace(" ", "")
    # Accept Arabic-Indic digits too.
    cleaned = cleaned.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    return value if value > 0 else None
