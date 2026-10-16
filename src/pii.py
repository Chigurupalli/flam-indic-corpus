"""PII redaction: Indian phone numbers, emails, Aadhaar, PAN.
Handles Devanagari digits. Order matters (email -> grouped Aadhaar -> PAN ->
ungrouped Aadhaar -> phone -> landline) so a 12-digit Aadhaar is not half-eaten as a phone.
"""
import re
from collections import Counter

D = "0-9\u0966-\u096f"
_NOT_DIGIT_BEFORE = rf"(?<![{D}])"
_NOT_DIGIT_AFTER = rf"(?![{D}])"

EMAIL = re.compile(r"(?<![A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
AADHAAR_GROUPED = re.compile(
    rf"{_NOT_DIGIT_BEFORE}[2-9\u0968-\u096f][{D}]{{3}}([ \-])[{D}]{{4}}\1[{D}]{{4}}{_NOT_DIGIT_AFTER}")
AADHAAR_PLAIN = re.compile(rf"{_NOT_DIGIT_BEFORE}[2-9\u0968-\u096f][{D}]{{11}}{_NOT_DIGIT_AFTER}")
PAN = re.compile(r"(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])")
PHONE = re.compile(
    rf"{_NOT_DIGIT_BEFORE}(?:(?:\+|00)[ \-]?91[ \-]?|91[ \-]?|0)?[6-9\u096c-\u096f][{D}]{{4}}[ \-.]?[{D}]{{5}}{_NOT_DIGIT_AFTER}")
LANDLINE = re.compile(r"(?<![0-9])\(?0[0-9]{2,4}\)?[ \-][0-9]{6,8}(?![0-9])")
_CONTEXT = re.compile(r"aadhaar|aadhar|adhar|uid|आधार", re.I)
_DEV_TO_ASCII = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}

_D = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
      [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],
      [8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_P = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
      [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(num: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def _digits(s):
    return re.sub(rf"[^{D}]", "", s).translate(_DEV_TO_ASCII)


def _phone_ok(s, has_plus):
    d = _digits(s)
    core = d[-10:]
    # 8000000000-style round numbers are quantities, not phones (unless written +91...)
    if not has_plus and core.endswith("00000"):
        return False
    return True


def redact(text: str):
    counts = Counter()

    def sub(tag):
        def f(m):
            counts[tag] += 1
            return f"<{tag}>"
        return f

    text = EMAIL.sub(sub("EMAIL"), text)
    text = AADHAAR_GROUPED.sub(sub("AADHAAR"), text)
    text = PAN.sub(sub("PAN"), text)

    def aadhaar_plain(m):
        d = _digits(m.group(0))
        before = text_cur[max(0, m.start() - 40):m.start()]
        if verhoeff_ok(d) or _CONTEXT.search(before):
            counts["AADHAAR"] += 1
            return "<AADHAAR>"
        return m.group(0)
    text_cur = text
    text = AADHAAR_PLAIN.sub(aadhaar_plain, text)

    def phone(m):
        s = m.group(0)
        if _phone_ok(s, s.lstrip().startswith(("+", "00"))):
            counts["PHONE"] += 1
            return "<PHONE>"
        return s
    text = PHONE.sub(phone, text)
    text = LANDLINE.sub(sub("PHONE"), text)
    return text, counts


def count_phones(text: str) -> int:
    return len(PHONE.findall(text))
