from __future__ import annotations


def jq_to_qmt_code(code: str | None) -> str | None:
    if code is None:
        return None

    text = str(code)
    if not text or "." not in text:
        return text

    symbol, suffix = text.rsplit(".", 1)
    suffix_upper = suffix.upper()
    if suffix_upper == "XSHE":
        return f"{symbol}.SZ"
    if suffix_upper == "XSHG":
        return f"{symbol}.SH"
    return text


def qmt_to_jq_code(code: str | None) -> str | None:
    if code is None:
        return None

    text = str(code)
    if not text or "." not in text:
        return text

    symbol, suffix = text.rsplit(".", 1)
    suffix_upper = suffix.upper()
    if suffix_upper == "SZ":
        return f"{symbol}.XSHE"
    if suffix_upper == "SH":
        return f"{symbol}.XSHG"
    return text
