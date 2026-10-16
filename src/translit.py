"""Script-agnostic consonant 'skeleton' used for cross-script contamination checks.

Devanagari and romanised Hindi are both mapped to the same reduced alphabet:
vowels are dropped (Hinglish vowel spelling is inconsistent: nahi/nahin/nhi),
aspirated/retroflex/dental distinctions collapse, 'ch'->C, 'sh'->S.
It is deliberately lossy: it is a *candidate generator* with a containment threshold.
"""
import re
import unicodedata

_DEV = {
    "क": "k", "ख": "k", "ग": "g", "घ": "g", "ङ": "n",
    "च": "C", "छ": "C", "ज": "j", "झ": "j", "ञ": "n",
    "ट": "t", "ठ": "t", "ड": "d", "ढ": "d", "ण": "n",
    "त": "t", "थ": "t", "द": "d", "ध": "d", "न": "n",
    "प": "p", "फ": "p", "ब": "b", "भ": "b", "म": "m",
    "य": "", "र": "r", "ल": "l", "व": "v", "श": "S", "ष": "S", "स": "s", "ह": "",
    "ं": "n",
}
_LAT = {"w": "v", "z": "j", "q": "k", "c": "k", "f": "p", "x": "k"}
_TABLE = {ord(k): v for k, v in _DEV.items()}
_TABLE.update({ord(k): v for k, v in _LAT.items()})
for i, c in enumerate("०१२३४५६७८९"):
    _TABLE[ord(c)] = str(i)
for c in "aeiouyh":
    _TABLE[ord(c)] = ""

_DEV_FINAL_NASAL = re.compile("[ंँ](?![\u0900-\u097f])")
_LAT_FINAL_NASAL = re.compile(r"(?<=[aeiou])[nm](?![a-z])")
_NOT_ALNUM = re.compile(r"[^A-Za-z0-9]")
_REPEAT = re.compile(r"(.)\1+")


def skeleton(text: str) -> str:
    t = unicodedata.normalize("NFC", text).casefold()
    t = _DEV_FINAL_NASAL.sub("", t)
    t = re.sub(r"chh|ch", "C", t)
    t = t.replace("sh", "S")
    t = _LAT_FINAL_NASAL.sub("", t)
    t = t.translate(_TABLE)
    t = _NOT_ALNUM.sub("", t)
    return _REPEAT.sub(r"\1", t)
