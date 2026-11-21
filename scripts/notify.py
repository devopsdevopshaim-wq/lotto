#!/usr/bin/env python3
"""Email the owner after each scored draw of the challenge, through Maton (api.maton.ai).

Runs after scripts/learn.py in the results workflow. Uses the MATON_API_KEY secret and the Gmail account connected at
maton.ai; the message goes to that same account, so no address is stored here. Each draw is sent once: the draw number is
added to "notified" in learn/state.json, which the workflow commits. Without a key it prints a note and does nothing.
"""
import base64, json, os, sys, urllib.error, urllib.request
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from pathlib import Path
from zoneinfo import ZoneInfo

STATE = Path(__file__).resolve().parent.parent / "learn" / "state.json"
BASES = ["https://api.maton.ai", "https://gateway.maton.ai"]
SITE = "https://devopsdevopshaim-wq.github.io/lotto/lotto.html#challenge"
E_HITS = 36 / 37


def maton(path, body=None):
    key = os.environ.get("MATON_API_KEY", "").strip()
    last = (0, {"error": "unreachable"})
    for base in BASES:
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     method="POST" if body is not None else "GET",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "lotto-notify"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            last = (e.code, {"error": e.read()[:300].decode("utf-8", "replace")})
            if e.code != 404 and e.code < 500:
                return last
        except urllib.error.URLError as e:
            last = (0, {"error": str(e)})
    return last


def nums(a, bold=()):
    return " · ".join(f"<b>{x}</b>" if x in bold else str(x) for x in a)


def build(st, r):
    res, R, n = r["result"], st["rounds"], st.get("next")
    hit = sorted(set(r["nums"]) & set(res["nums"]))
    k, tot = len(R), sum(x["hits"] for x in R)
    wins, sh = sum(x["hits"] >= 3 for x in R), sum(x["strong_hit"] for x in R)
    verdict = "זכייה! (3 מספרים ומעלה)" if r["hits"] >= 3 else "אין זכייה (זכייה מתחילה ב־3 מספרים)"
    rows = "".join(f"<tr><td>{x['draw']} ({x['result']['date'][:5]})</td><td>{nums(x['nums'])} + {x['strong']}</td>"
                   f"<td>{nums(x['result']['nums'])} + {x['result']['strong']}</td><td>{x['hits']}{' + חזק' if x['strong_hit'] else ''}</td></tr>" for x in R)
    when = ""
    if n:
        t = datetime.fromisoformat(n["registered_at"]).astimezone(ZoneInfo("Asia/Jerusalem"))
        when = t.strftime("%d/%m/%Y %H:%M")
    html = f"""<div dir="rtl" style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6;color:#161a23">
<h2 style="margin:0 0 6px">בדיקת הגרלה {r['draw']} · {res['date']}</h2>
<p style="margin:0 0 12px"><b>התוצאה:</b> {nums(res['nums'])} · חזק {res['strong']}</p>
<p style="margin:0 0 4px"><b>הניחוש שנרשם מראש:</b> {nums(r['nums'], hit)} · חזק {r['strong']}</p>
<p style="margin:0 0 12px"><b>זוהו: {r['hits']} {'מספר' if r['hits'] == 1 else 'מספרים'}{' (' + ', '.join(map(str, hit)) + ')' if hit else ''}.</b>
 {'החזק עלה.' if r['strong_hit'] else 'החזק לא עלה.'} {verdict}.</p>
<h3 style="margin:16px 0 6px">מעקב מצטבר</h3>
<table cellpadding="6" style="border-collapse:collapse;border:1px solid #d7deeb"><tr style="background:#f2f5fa"><th align="right">הגרלה</th><th align="right">ניחוש</th><th align="right">התוצאה</th><th align="right">זוהו</th></tr>{rows}</table>
<p style="margin:8px 0 12px">סך הכול: {k} סיבובים, {tot} מספרים זוהו (צפוי במזל: {E_HITS * k:.1f}). זכיות: {wins}. החזק: {sh} מתוך {k}.{' מוקדם לשפוט, צריך 20–30 סיבובים.' if k < 20 else ''}</p>
<h3 style="margin:16px 0 6px">ההמלצה להגרלה הבאה{f" ({n['draw']})" if n else ''}</h3>
{f'<p style="font-size:20px;margin:0 0 6px"><b>{nums(n["nums"])} · חזק {n["strong"]}</b></p><p style="margin:0 0 12px;color:#5d6577">נרשם אוטומטית ב־{when} (שעון ישראל), לפני ההגרלה. לכל צירוף יש אותו סיכוי: 1 ל־24 ל־3 מספרים, 1 ל־16.3 מיליון לפרס הראשון.</p>' if n else '<p>הניחוש הבא יירשם אחרי עדכון הנתונים.</p>'}
<p style="margin:0"><a href="{SITE}">לעמוד האתגר באתר</a></p>
<p style="margin:16px 0 0;color:#5d6577;font-size:13px">שחקו רק בסכום שנוח לכם להפסיד.</p></div>"""
    text = (f"בדיקת הגרלה {r['draw']} · {res['date']}\nהתוצאה: {' '.join(map(str, res['nums']))}, חזק {res['strong']}\n"
            f"הניחוש: {' '.join(map(str, r['nums']))}, חזק {r['strong']}\nזוהו: {r['hits']} ({', '.join(map(str, hit)) or '-'}). {verdict}.\n"
            f"מעקב: {k} סיבובים, {tot} מספרים (מזל {E_HITS * k:.1f}), זכיות {wins}.\n"
            + (f"ההמלצה להגרלה {n['draw']}: {' '.join(map(str, n['nums']))}, חזק {n['strong']}\n" if n else "") + SITE)
    return f"לוטו · בדיקת הגרלה {r['draw']}", text, html


def main():
    st = json.loads(STATE.read_text(encoding="utf-8"))
    if not st.get("rounds"):
        print("no scored rounds yet"); return
    r = st["rounds"][-1]
    if r["draw"] in st.setdefault("notified", []):
        print(f"draw {r['draw']} already sent"); return
    if not os.environ.get("MATON_API_KEY", "").strip():
        print("::notice::MATON_API_KEY is not set in this repository, so no email was sent."); return
    code, prof = maton("/google-mail/gmail/v1/users/me/profile")
    me = prof.get("emailAddress") if code == 200 else None
    if not me:
        print(f"::warning::Maton/Gmail profile failed ({code}): {str(prof)[:200]}"); return
    subject, text, html = build(st, r)
    msg = MIMEMultipart("alternative"); msg["To"] = me; msg["Subject"] = str(Header(subject, "utf-8"))
    msg.attach(MIMEText(text, "plain", "utf-8")); msg.attach(MIMEText(html, "html", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode().rstrip("=")
    code, out = maton("/google-mail/gmail/v1/users/me/messages/send", {"raw": raw})
    if code != 200:
        print(f"::warning::Maton/Gmail send failed ({code}): {str(out)[:200]}"); return
    st["notified"].append(r["draw"])
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"sent the update for draw {r['draw']}")


if __name__ == "__main__":
    main()
