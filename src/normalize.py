"""Text normalisation. Goal: things that are the same compare as the same.

Decisions (also in DECISIONS.md):
* NFC. Devanagari nukta letters like U+0958 are composition-exclusions, so NFC
  rewrites them as base + U+093C; the two ways of typing them end up identical.
* Invisible/format characters are removed: ZWSP, WORD JOINER, BOM, soft hyphen,
  bidi marks, AND ZWJ/ZWNJ. ZWJ/ZWNJ only change how a conjunct is *drawn* in
  Devanagari, and sources use them inconsistently, so keeping them would make
  identical words compare as different.
* Whitespace: tabs/nbsp/ideographic space -> one space; spaces around newlines
  removed; 3+ newlines -> one blank line. Paragraph structure is kept.
"""
import re
import unicodedata

_DROP = dict.fromkeys(map(ord, (
    "\u200b\u200c\u200d\u2060\ufeff\u00ad\u200e\u200f"
    "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\u180e")), None)
_CTRL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x9f]")
_HSPACE = re.compile(r"[^\S\n]+")
_NL_SPACE = re.compile(r" ?\n ?")
_MANY_NL = re.compile(r"\n{3,}")
_DEV_DIGITS = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}
_TOKEN = re.compile(r"[\w\u0900-\u0963\u0966-\u097f\u0300-\u036f]+")


def normalize(text: str) -> str:
    text = text.translate(_DROP)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u2028", "\n").replace("\u2029", "\n\n")
    text = _CTRL.sub("", text)
    text = _HSPACE.sub(" ", text)
    text = _NL_SPACE.sub("\n", text)
    text = _MANY_NL.sub("\n\n", text)
    return text.strip()


def tokens(text: str):
    """Aggressive comparison tokens: casefolded, Devanagari digits -> ASCII,
    punctuation (incl. danda) dropped. NOTE: \\w alone would split Devanagari
    words at every matra (Mn/Mc are not \\w), hence the explicit block ranges."""
    text = unicodedata.normalize("NFC", text.translate(_DROP)).casefold().translate(_DEV_DIGITS)
    return _TOKEN.findall(text)
