#!/usr/bin/env python3
"""Append new Israeli Lotto draws to lotto.csv.

Primary source: paisresults.co.il (paginated archive). Every draw is cross-checked
against lottoplus.co.il where both list it; any disagreement aborts without writing.
lotto.csv keeps the Pais export layout and Windows-1255 encoding.
"""
import html, re, sys, time, urllib.request
from pathlib import Path

CSV = Path(__file__).resolve().parent.parent / "lotto.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
PRIMARY = "https://www.paisresults.co.il/index.php?p={page}"
CHECK = "https://lottoplus.co.il/lotto-result/"


def fetch(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "he-IL,he;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"fetch failed ({attempt + 1}/3) {url}: {e}", file=sys.stderr)
            time.sleep(3 * (attempt + 1))
    return None


def text_of(page):
    page = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def valid(d):
    nums, strong = d["nums"], d["strong"]
    return len(set(nums)) == 6 and all(1 <= n <= 37 for n in nums) and 1 <= strong <= 7


def parse_primary(page):
    out = {}
    pat = re.compile(r"בהגרלה מספר:\s*(\d+)\s*מתאריך:\s*(\d{2}/\d{2}/\d{4})\s*עלו המספרים:\s*([\d\s,]+?)\s*המספר החזק:\s*(\d)")
    for m in pat.finditer(text_of(page)):
        nums = [int(x) for x in re.findall(r"\d+", m.group(3))]
        if len(nums) == 6:
            out[int(m.group(1))] = {"id": int(m.group(1)), "date": m.group(2), "nums": sorted(nums), "strong": int(m.group(4))}
    return out


def parse_check(page):
    out = {}
    t = text_of(page)
    pat = re.compile(r"הגרלה מספר:\s*(\d+)\s*מתאריך:\s*(\d{2}/\d{2}/\d{4}).*?לצפיה בטבלת הזכיות\s*((?:\d{1,2}\s+){6}\d)\b")
    for m in pat.finditer(t):
        v = [int(x) for x in m.group(3).split()]
        out[int(m.group(1))] = {"id": int(m.group(1)), "date": m.group(2), "nums": sorted(v[:6]), "strong": v[6]}
    return out


def load_csv():
    raw = CSV.read_bytes()
    try:
        text, enc = raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        text, enc = raw.decode("cp1255"), "cp1255"
    lines = text.splitlines()
    ids = set()
    for line in lines[1:]:
        c = line.split(",")
        if c and c[0].strip().isdigit():
            ids.add(int(c[0]))
    return lines, ids, enc


def main():
    lines, ids, enc = load_csv()
    # current-format draw numbers are 2234+; older rows use year-coded numbers
    known_max = max(i for i in ids if i < 6000)
    print(f"lotto.csv: {len(lines) - 1} rows, latest draw {known_max}")

    found = {}
    for page in range(1, 60):
        p = fetch(PRIMARY.format(page=page))
        if not p:
            break
        got = parse_primary(p)
        if not got:
            break
        found.update(got)
        if min(got) <= known_max + 1:
            break
    new = {k: v for k, v in found.items() if k > known_max}
    if not new:
        print("No new draws.")
        return 0

    bad = [d for d in new.values() if not valid(d)]
    if bad:
        print(f"Invalid draws from source, aborting: {bad}", file=sys.stderr)
        return 1
    expected = set(range(known_max + 1, max(new) + 1))
    missing = sorted(expected - set(new))
    if missing:
        print(f"Source is missing draws {missing}; aborting so the file stays contiguous.", file=sys.stderr)
        return 1

    chk_page = fetch(CHECK)
    chk = parse_check(chk_page) if chk_page else {}
    overlap = [k for k in new if k in chk]
    for k in overlap:
        a, b = new[k], chk[k]
        if (a["date"], a["nums"], a["strong"]) != (b["date"], b["nums"], b["strong"]):
            print(f"Sources disagree on draw {k}: {a} vs {b}; aborting.", file=sys.stderr)
            return 1
    print(f"Cross-checked {len(overlap)} draw(s) against lottoplus.co.il" + ("" if overlap else " (none overlapped)"))

    rows = [f"{d['id']},{d['date']},{','.join(f'{n:02d}' for n in d['nums'])},{d['strong']},,,"
            for d in sorted(new.values(), key=lambda d: -d["id"])]
    out = "\n".join([lines[0], *rows, *lines[1:]]) + "\n"
    CSV.write_bytes(out.encode(enc))
    print(f"Added {len(rows)} draws: {min(new)}..{max(new)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
