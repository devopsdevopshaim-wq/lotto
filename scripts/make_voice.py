#!/usr/bin/env python3
"""Record the site's read-aloud texts with Azure neural TTS (he-IL-HilaNeural).

Reads voice/texts.json (written by scripts/voice_texts.mjs), records only texts whose hash has no MP3 yet,
deletes recordings that are no longer used, and writes voice/manifest.json {hash: file} for the page.
Env: AZURE_SPEECH_KEY, AZURE_SPEECH_REGION (e.g. westeurope). --dry-run prints what would be recorded.
"""
import json, os, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

VOICE_DIR = Path(__file__).resolve().parent.parent / "voice"
VOICE = "he-IL-HilaNeural"
FORMAT = "audio-24khz-96kbitrate-mono-mp3"


def ssml(text):
    return (f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='he-IL'>"
            f"<voice name='{VOICE}'><prosody rate='-4%'>{escape(text)}</prosody></voice></speak>")


def synthesize(text, key, region):
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml(text).encode("utf-8"),
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": FORMAT, "User-Agent": "lotto-voice"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                sys.exit(f"Azure refused the key ({e.code}). Check the AZURE_SPEECH_KEY and AZURE_SPEECH_REGION secrets.")
            if e.code == 429 or e.code >= 500:
                time.sleep(5 * (attempt + 1)); continue
            sys.exit(f"Azure error {e.code}: {e.read()[:300]!r}")
        except urllib.error.URLError as e:
            print(f"network error ({attempt + 1}/4): {e}", file=sys.stderr); time.sleep(5 * (attempt + 1))
    sys.exit("Azure did not answer after 4 attempts.")


def main():
    dry = "--dry-run" in sys.argv
    texts = json.loads((VOICE_DIR / "texts.json").read_text(encoding="utf-8"))
    man_path = VOICE_DIR / "manifest.json"
    old = json.loads(man_path.read_text(encoding="utf-8")).get("files", {}) if man_path.exists() else {}
    want = {t["hash"]: t["text"] for t in texts.values()}
    todo = {h: t for h, t in want.items() if not (h in old and (VOICE_DIR / old[h]).exists())}
    print(f"{len(want)} texts, {len(todo)} to record ({sum(map(len, todo.values()))} characters)")
    if dry:
        for h, t in todo.items():
            print(f"  {h}: {t[:70]}…")
        return
    key, region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
    if not key or not region:
        sys.exit("AZURE_SPEECH_KEY and AZURE_SPEECH_REGION must be set.")
    files = {h: old[h] for h in want if h not in todo}
    for h, t in todo.items():
        audio = synthesize(t, key, region)
        (VOICE_DIR / f"{h}.mp3").write_bytes(audio)
        files[h] = f"{h}.mp3"
        print(f"  recorded {h}.mp3 ({len(audio) // 1024} KB)")
    for f in VOICE_DIR.glob("*.mp3"):
        if f.name not in files.values():
            f.unlink(); print(f"  removed {f.name}")
    man_path.write_text(json.dumps({"voice": VOICE, "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "files": files}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
