from src.normalize import normalize, tokens
from src.langid import detect
from src.pii import redact, verhoeff_ok, verhoeff_check_digit
from src.filters import quality_reason
from src.translit import skeleton
from src.dedup import NearDedup


def test_normalize_invisible_and_nukta():
    assert normalize("क\u093c") == normalize("\u0958")          # nukta forms compare equal
    assert normalize("क\u200d\u200c\u200bख  \t ग\r\n\r\n\r\n\r\nघ") == "कख ग\n\nघ"
    assert tokens("राम, राम। १२३") == ["राम", "राम", "123"]


def test_langid():
    assert detect("मुझे यह बात बहुत अच्छी लगती है") == "hi"
    assert detect("आज मौसम good है और मैं office जा रहा हूँ") == "hi"
    assert detect("mujhe ye baat bahut achhi lagti hai yaar") == "hi-Latn"
    assert detect("This is a plain English sentence about the weather today") == "en"
    assert detect("12 34 56") == "other"


def test_pii_positive():
    t, c = redact("ph +91 98765 43210, 9876543210, 098765-43210, ९८७६५४३२१०, mail a.b@x.co.in, ABCDE1234F, 2345 6789 0123")
    assert "<PHONE>" in t and "<EMAIL>" in t and "<PAN>" in t and "<AADHAAR>" in t
    assert not any(ch.isdigit() for ch in t.replace("<PHONE>", "").replace("<AADHAAR>", ""))


def test_pii_negative():
    s = "वर्ष 2023, कीमत ₹1,50,000, संख्या 1234567890, आबादी 8000000000, ISBN 978-3-16-148410-0"
    t, c = redact(s)
    assert t == s and not c


def test_aadhaar_plain_needs_checksum_or_context():
    n = "23456789012"
    ok = n + verhoeff_check_digit(n)
    assert verhoeff_ok(ok)
    assert redact(f"id {ok}")[0] == "id <AADHAAR>"
    bad = n + str((int(verhoeff_check_digit(n)) + 1) % 10)
    assert redact(f"num {bad}")[0] == f"num {bad}"
    assert redact(f"आधार {bad}")[0] == "आधार <AADHAAR>"


def test_filters_keep_unusual_but_legit():
    assert quality_reason("जैसा बोओगे वैसा काटोगे", "hi") is None                 # proverb
    assert quality_reason("१२ ३४ ५६ ७८\n९० १२ ३४ ५६", "hi") is None               # numeric table
    assert quality_reason("1 | 2 | 3\n4 | 5 | 6\n7 | 8 | 9", "hi") is None
    poem = "चाँद तारे चमकते हैं\nचाँद तारे चमकते हैं\nरात बहुत हसीन है"
    assert quality_reason(poem, "hi") is None


def test_filters_drop_bad():
    assert quality_reason("<div><p>a</p><span>b</span></div>", "hi").startswith("markup")
    assert quality_reason("à¤¨à¤®à¤¸à¥à¤¤à¥‡ à¤¦à¥‹à¤¸à¥à¤¤", "hi").startswith("mojibake")
    assert quality_reason("राम " * 30, "hi").startswith("repetitive")


def test_cross_script_skeleton():
    a = skeleton("मुझे यह बात बहुत अच्छी लगती है कि तुम हमेशा सच बोलते हो")
    b = skeleton("mujhe yeh baat bahut achchi lagti hai ki tum hamesha sach bolte ho")
    assert a == b


def test_near_dedup():
    nd = NearDedup(threshold=0.8)
    base = "यह एक लंबा वाक्य है जिसमें कई शब्द हैं और यह दो बार आता है " * 5
    assert nd.query_add("a", base)[0] is None
    assert nd.query_add("b", base + "अंत")[0] == "a"
    assert nd.query_add("c", "बिल्कुल अलग पाठ जो किसी से मेल नहीं खाता और काफी लंबा है " * 5)[0] is None


def _det(text):
    from src.contamination import Detector
    return Detector([{"eval_id": "e0", "text": text, "lang": "hi", "source": "s", "doc_id": "d"}])


EV = "मुझे यह बात बहुत अच्छी लगती है कि तुम हमेशा सच बोलते हो और मेहनत करते हो"


def test_contamination_methods():
    det = _det(EV)
    m, _ = det.check({"text": "शुरू " + EV + " अंत", "lang": "hi"})
    assert m[0][0] == "exact"
    m, _ = det.check({"text": "शुरू " + EV.replace(" ", "  ").replace("है", "है,").upper() + " अंत", "lang": "hi"})
    assert m[0][0] == "normalized"
    m, _ = det.check({"text": " ".join(EV.split()[:13]) + " कुछ और शब्द यहाँ जोड़े गए हैं", "lang": "hi"})
    assert m[0][0] == "near"
    m, rej = det.check({"text": "बिल्कुल अलग विषय पर एक लंबा पाठ जिसमें कोई समानता नहीं है", "lang": "hi"})
    assert not m


def test_contamination_cross_script():
    det = _det(EV)
    latin = "intro mujhe yeh baat bahut achchi lagti hai ki tum hamesha sach bolte ho aur mehnat karte ho outro"
    m, _ = det.check({"text": latin, "lang": "hi-Latn"})
    assert m[0][0] == "cross_script"
    m, _ = det.check({"text": "aaj mausam bahut accha hai chalo bahar ghoomne chalte hain", "lang": "hi-Latn"})
    assert not m
