"""Quality filters. Each returns a *reason string* (the ledger needs it) or None.

Deliberate non-rules (so legitimate-but-unusual text survives):
* NO blanket minimum length: a 2-line proverb or couplet is valid Hindi.
  Only Latin-script text needs >= MIN_TOKENS_LATIN tokens (handled in langid).
* Tables of numbers: digits count as content; symbol/markup ratios exclude digits,
  commas, periods, pipes and slashes.
* Repetition rules only fire at >= REPEAT_MIN_TOKENS tokens, so refrains in poems survive.
"""
import re
from collections import Counter
from . import config as C
from .normalize import tokens
from .pii import count_phones

_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
_HTML_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]{0,200})?/?>")
_WIKI = re.compile(r"\{\{|\}\}|\[\[|\]\]|^\s*\|-|^\{\|", re.M)
_MOJI = re.compile(r"à[¤¥]|Ã[\u0080-\u00bf]|â€[™œ\u009d“”¢]")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF]")
_RESIDUE = re.compile(r"[{}\[\]<>#~^\\=]")
_SPAM = re.compile(
    r"click here|buy now|free download|casino|online betting|satta ?matka|lottery winner|"
    r"whatsapp (?:me|us)|call now|मुफ्त डाउनलोड|यहाँ क्लिक करें|यहां क्लिक करें|सट्टा मटका|लॉटरी जीत", re.I)
_BOILER = re.compile(
    r"all rights reserved|©|copyright|cookie|privacy policy|terms (?:of use|and conditions)|"
    r"subscribe|follow us|read more|share this|sign in|log in|advertisement|"
    r"सर्वाधिकार सुरक्षित|कॉपीराइट|और पढ़ें|अधिक पढ़ें|सब्सक्राइब|हमें फॉलो करें|विज्ञापन|गोपनीयता नीति", re.I)


def garbled_reason(text: str):
    """Encoding damage. Checked BEFORE language id so garbage is reported as garbage,
    not mislabelled 'other'."""
    if text.count("\ufffd") > C.MAX_REPLACEMENT_CHARS:
        return "mojibake_replacement_chars"
    if len(_MOJI.findall(text)) >= 2:
        return "mojibake_utf8_as_latin1"
    return None


def quality_reason(text: str, lang: str):
    n = len(text)
    if not any(ch.isalnum() for ch in text):
        return "no_content"

    # markup
    if len(_HTML_TAG.findall(text)) > C.MAX_HTML_TAGS:
        return "markup_html"
    if len(_WIKI.findall(text)) > C.MAX_WIKI_MARKERS:
        return "markup_wikitext"
    if len(_RESIDUE.findall(text)) / n > C.MARKUP_RESIDUE_MAX:
        return "markup_residue"

    g = garbled_reason(text)
    if g:
        return g

    toks = tokens(text)
    nt = len(toks)

    # spam
    urls = _URL.findall(text)
    if len(urls) >= 3 and sum(len(u) for u in urls) / n > C.MAX_URL_SHARE:
        return "spam_url_heavy"
    if count_phones(text) > C.MAX_PHONES_IN_DOC:
        return "spam_contact_list"
    hits = len(_SPAM.findall(text))
    if hits >= 3 or (hits >= 2 and nt < 40):
        return "spam_phrases"
    if len(_EMOJI.findall(text)) / n > C.SYMBOL_RATIO_MAX:
        return "emoji_heavy"
    if nt >= C.REPEAT_MIN_TOKENS:
        cnt = Counter(toks)
        if cnt.most_common(1)[0][1] / nt > C.REPEAT_TOP_SHARE:
            return "repetitive_top_token"
        if len(cnt) / nt < C.REPEAT_UNIQUE_RATIO:
            return "repetitive_low_diversity"

    # boilerplate (short lines that are navigation/footer chatter)
    lines = [l for l in text.split("\n") if l.strip()]
    if lines:
        b = sum(1 for l in lines if len(l) < C.BOILERPLATE_LINE_MAXLEN and _BOILER.search(l))
        if b / len(lines) >= C.BOILERPLATE_LINE_SHARE:
            return "boilerplate"
    return None
