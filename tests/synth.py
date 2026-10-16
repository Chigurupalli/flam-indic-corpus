"""Builds a small messy raw dir (jsonl.gz, MediaWiki xml.bz2, csv, truncated gz, bad lines)."""
import bz2, csv, gzip, json, os, random

HI = ("भारत एक विशाल देश है जहाँ अनेक भाषाएँ बोली जाती हैं और लोग मिलकर रहते हैं नदियाँ पहाड़ जंगल खेत गाँव शहर "
      "किसान मौसम बारिश सर्दी गर्मी त्योहार दिवाली होली संगीत कविता कहानी विद्यालय किताब पढ़ना लिखना बच्चे बूढ़े "
      "सुबह शाम रात दिन समय बाजार दुकान सब्जी फल दूध पानी रोटी चावल दाल मिठाई मेहमान परिवार दोस्त सपना मेहनत सफलता").split()
HL = ("mujhe ye baat bahut achhi lagti hai kyunki tum hamesha sach bolte ho aur main bhi koshish karta hoon "
      "kal hum movie dekhne chalenge toh tum jaldi aana kya tum bhi aaoge nahi yaar mera mood theek nahi hai "
      "office mein bahut kaam hai lekin phir bhi weekend par ghoomne jayenge").split()
EN = "the quick brown fox jumps over the lazy dog and this is a long english sentence that should be dropped".split()


def hi_doc(rng, n):
    return " ".join(rng.choice(HI) for _ in range(n)) + " ।"


def build(raw, seed=7, n_hi=400, n_hl=120):
    rng = random.Random(seed)
    os.makedirs(os.path.join(raw, "news_jsonl"), exist_ok=True)
    os.makedirs(os.path.join(raw, "wiki_xml"), exist_ok=True)
    os.makedirs(os.path.join(raw, "hinglish_csv"), exist_ok=True)
    docs = [hi_doc(rng, rng.randint(15, 60)) for _ in range(n_hi)]
    lines = []
    for i, d in enumerate(docs):
        lines.append(json.dumps({"id": i, "text": d, "lang": "wrong-label"}, ensure_ascii=False))
    lines.append(json.dumps({"text": docs[0]}, ensure_ascii=False))                       # exact dup
    lines.append(json.dumps({"text": docs[1].replace("है", "है ") + " "}, ensure_ascii=False))  # whitespace dup
    lines.append(json.dumps({"text": docs[2] + " " + rng.choice(HI)}, ensure_ascii=False))     # near dup
    lines.append(json.dumps({"text": "\u200bज़्\u200dयादा " + docs[3]}, ensure_ascii=False))
    for d in docs[20:100]:                                                                      # many exact dups
        lines.append(json.dumps({"text": d}, ensure_ascii=False))
    lines.append("{this is not json")
    lines.append(json.dumps({"nope": 1}))
    lines.append(json.dumps({"text": "संपर्क करें 9876543210 या test.user@example.com, आधार 2345 6789 0123, PAN ABCDE1234F, वर्ष 2023 कीमत ₹1,50,000 संख्या 1234567890 और मेरा नंबर ९८७६५४३२१०"}, ensure_ascii=False))
    lines.append(json.dumps({"text": "<div><p>नमस्ते</p><span>दोस्त</span><a href='x'>link</a></div>"}, ensure_ascii=False))
    lines.append(json.dumps({"text": "à¤¨à¤®à¤¸à¥à¤¤à¥‡ à¤¦à¥‹à¤¸à¥à¤¤ à¤•à¥ˆà¤¸à¥‡ à¤¹à¥‹"}))
    lines.append(json.dumps({"text": "click here buy now casino free download " * 3 + "https://a.b/c https://d.e/f https://g.h/i"}))
    lines.append(json.dumps({"text": " ".join(EN)}))
    lines.append(json.dumps({"text": "जैसा बोओगे वैसा काटोगे"}, ensure_ascii=False))          # short proverb must survive
    lines.append(json.dumps({"text": "१२ ३४ ५६ ७८\n९० १२ ३४ ५६"}, ensure_ascii=False))        # digits-only table
    lines.append(json.dumps({"text": "राम राम राम राम राम राम राम राम राम राम राम राम"}, ensure_ascii=False))
    # cross-script copy of doc 10 and 11 in romanised form
    lines.append(json.dumps({"text": "bharat ek vishal desh hai jahan anek bhashaen boli jati hain aur log milkar rahte hain " + HL[0]}))
    with gzip.open(os.path.join(raw, "news_jsonl", "part1.jsonl.gz"), "wt", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    # truncated gzip
    full = gzip.compress(("\n".join(json.dumps({"text": hi_doc(rng, 20)}, ensure_ascii=False) for _ in range(300))).encode("utf-8"))
    with open(os.path.join(raw, "news_jsonl", "part2_truncated.jsonl.gz"), "wb") as f:
        f.write(full[: len(full) // 2])
    # MediaWiki XML
    pages = []
    for i in range(60):
        body = "'''शीर्षक''' {{Infobox|x=1}} " + hi_doc(rng, 30) + "<ref>स्रोत</ref> [[भारत|देश]] [[श्रेणी:परीक्षण]]\n== उपशीर्षक ==\n* " + hi_doc(rng, 20)
        pages.append(f"<page><title>पन्ना {i}</title><ns>0</ns><revision><text>{body}</text></revision></page>")
    pages.append("<page><title>R</title><ns>0</ns><redirect title='x'/><revision><text>#REDIRECT [[x]]</text></revision></page>")
    pages.append("<page><title>वार्ता</title><ns>1</ns><revision><text>बातचीत</text></revision></page>")
    xml = '<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.10/">' + "".join(pages) + "</mediawiki>"
    with bz2.open(os.path.join(raw, "wiki_xml", "hiwiki-sample.xml.bz2"), "wt", encoding="utf-8") as f:
        f.write(xml)
    # Hinglish CSV
    with open(os.path.join(raw, "hinglish_csv", "hing.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "hinglish", "english"])
        for i in range(n_hl):
            w.writerow([i, " ".join(rng.choice(HL) for _ in range(rng.randint(8, 20))), "translation"])
    with open(os.path.join(raw, "SOURCES.json"), "w") as f:
        json.dump([{"name": "synthetic", "url": "n/a", "license": "CC0", "downloaded": "2026-10-16"}], f)
    return docs
