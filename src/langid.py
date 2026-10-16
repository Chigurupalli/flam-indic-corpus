"""Language labelling: exactly one of  hi | hi-Latn | en | other.   Source labels are never used.

Script first, then words:
* Devanagari share of letters >= DEVANAGARI_MIN  -> "hi" (English words mixed in are fine),
  unless clear Marathi markers outweigh Hindi markers -> "other".
* Mostly Latin: romanised-Hindi function words decide hi-Latn vs en.
  (fastText-style LID calls most Hinglish "en", so we use our own word-list score.)
* Anything else, or no letters at all (e.g. a table of numbers) -> "other".
"""
import re
from . import config as C
from .normalize import tokens

_DEV_LETTER = re.compile(r"[\u0900-\u0963\u0971-\u097f]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")
# tags/URLs are Latin letters but say nothing about the language of the prose
_NOISE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]{0,200})?/?>|(?:https?://|www\.)\S+")

HINGLISH = frozenset("""
hai hain nahi nahin nhi nai kya kyu kyun kyon mein me_ aur ya toh tho bhi tha thi thhe
ko ka ki ke se pe par ye yeh wo woh vo kuch koi kaise kaisa kaisi kaun kab kahan kahaan
hum hame humein tum tumhe tumhein aap aapko aapka mera meri mere tera teri tere tu tujhe
mujhe mujhko apna apni apne unka unki unke inka inki inke uska uski uske iska iski iske
bahut bohot bhot accha acha achha achchha theek thik bhai yaar yar dost
ho hoga hogi honge hota hoti hote raha rahi rahe rha rhi rhe kar kare karo karna karta karti
kiya kiye gaya gayi gaye jana jaana aana aaya aayi chahiye chahta chahti
lekin magar abhi sab sabhi jab tab agar phir fir matlab bas sirf bilkul zaroor zarur
liye liya diya dena lena mat naa na_ haan han kuchh jyada zyada thoda thodi
""".replace("me_", "").replace("na_", "").split())

ENGLISH = frozenset("""
the is are was were be been and or of to in that it for with as on at by this these those
from you your i he she we they them his her their its not have has had do does did will would
can could should may might but if then so than there here what which who whom when where why
how all any some no yes my our me us an a
""".split())

MARATHI = frozenset("आहे आहेत आणि मध्ये होते म्हणून किंवा नाही काय आम्ही तुम्ही".split())
HINDI_MARK = frozenset("है हैं के की का में और से को पर एक यह था थी थे ने कि नहीं भी तो".split())


def script_counts(text):
    dev = len(_DEV_LETTER.findall(text))
    lat = len(_LATIN_LETTER.findall(text))
    other = sum(1 for ch in text if ch.isalpha()) - lat - sum(1 for ch in text if "\u0900" <= ch <= "\u097f" and ch.isalpha())
    return dev, lat, max(other, 0)


def detect(text: str) -> str:
    text = _NOISE.sub(" ", text)
    dev, lat, other = script_counts(text)
    total = dev + lat + other
    if total == 0:
        return "other"
    if dev / total >= C.DEVANAGARI_MIN:
        toks = tokens(text)
        mr = sum(1 for t in toks if t in MARATHI)
        hi = sum(1 for t in toks if t in HINDI_MARK)
        if mr >= 2 and mr > hi:
            return "other"
        return "hi"
    if lat / total >= C.LATIN_MIN:
        toks = [t for t in tokens(text) if not t.isdigit()]
        if len(toks) < C.MIN_TOKENS_LATIN:
            return "other"
        hi_hits = sum(1 for t in toks if t in HINGLISH)
        en_hits = sum(1 for t in toks if t in ENGLISH)
        n = len(toks)
        if hi_hits >= C.HINGLISH_MIN_HITS and hi_hits / n >= C.HINGLISH_MIN_RATIO and hi_hits >= en_hits * 0.5:
            return "hi-Latn"
        if n < 8 and hi_hits >= 1 and en_hits == 0:
            return "hi-Latn"
        if en_hits / n >= 0.08:
            return "en"
        return "other"
    return "other"
