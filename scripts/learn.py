#!/usr/bin/env python3
"""The self-learning challenge.

After every draw this script
  1. scores the ticket it registered for that draw *before* the draw (and every expert's ticket),
  2. updates the experts' weights by how many numbers each one caught (multiplicative weights / Hedge),
  3. registers its ticket for the next draw, with a timestamp, in learn/state.json.

The registered ticket is committed to git before the draw, so it cannot be changed after the result.
The first run warms the weights up on past draws; those rounds are not part of the public record.
"""
import csv, json, math, random, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "lotto.csv"
STATE = ROOT / "learn" / "state.json"
N, PICK, NS = 37, 6, 7
ETA = 0.1
WARMUP = 300
E_HITS = PICK * PICK / N


def load_draws():
    raw = CSV.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1255")
    out = []
    for row in csv.reader(text.splitlines()[1:]):
        try:
            i = int(row[0]); nums = sorted(int(x) for x in row[2:8]); s = int(row[8])
        except (ValueError, IndexError):
            continue
        if 2234 <= i < 6000 and len(set(nums)) == 6 and max(nums) <= N and 1 <= s <= NS:
            out.append({"id": i, "date": row[1], "nums": nums, "strong": s})
    out.sort(key=lambda d: d["id"])
    return out  # oldest first


def top(score, k=PICK, n=N):
    return sorted(sorted(range(1, n + 1), key=lambda x: (-score[x], x))[:k])


def experts(hist, seed):
    """Every expert's ticket for the draw after `hist` (oldest first)."""
    h = hist[::-1]  # newest first
    n = len(h)
    f = [0] * (N + 1); f100 = [0] * (N + 1); f30 = [0] * (N + 1); ew = [0.0] * (N + 1); gap = [None] * (N + 1)
    s100 = [0] * (NS + 1); sgap = [None] * (NS + 1)
    w = 1.0
    for t, d in enumerate(h):
        for x in d["nums"]:
            f[x] += 1; ew[x] += w
            if t < 100: f100[x] += 1
            if t < 30: f30[x] += 1
            if gap[x] is None: gap[x] = t
        if t < 100: s100[d["strong"]] += 1
        if sgap[d["strong"]] is None: sgap[d["strong"]] = t
        w *= 0.965
    gap = [n if g is None else g for g in gap]; sgap = [n if g is None else g for g in sgap]
    last = h[0]["nums"]
    # Markov (last 150 draws): what followed the numbers of the last draw
    mk = [0.0] * (N + 1); seen = [0] * (N + 1); tr = {}
    for t in range(min(150, n - 1)):
        for m in h[t + 1]["nums"]:
            seen[m] += 1
            for x in h[t]["nums"]:
                tr[(m, x)] = tr.get((m, x), 0) + 1
    for x in range(1, N + 1):
        mk[x] = sum(tr.get((m, x), 0) / seen[m] for m in last if seen[m]) + f100[x] / 1e4
    # pair affinity with the last draw (last 300 draws)
    pa = [0.0] * (N + 1)
    for d in h[:300]:
        a = d["nums"]
        hit = [m for m in last if m in a]
        if hit:
            for x in a:
                if x not in last: pa[x] += len(hit)
    pa = [v + f100[i] / 1e4 for i, v in enumerate(pa)]
    # k-nearest neighbours: the 30 past draws most like the last one, and what came after them
    sims = sorted(((len(set(h[t]["nums"]) & set(last)), -t, t) for t in range(1, n)), reverse=True)[:30]
    knn = [0.0] * (N + 1)
    for o, _, t in sims:
        for x in h[t - 1]["nums"]: knn[x] += o
    knn = [v + f100[i] / 1e4 for i, v in enumerate(knn)]
    due = [gap[x] / max(1.0, n / max(1, f[x])) if x else 0 for x in range(N + 1)]
    rnd = random.Random(seed)
    hot_s = top(s100, 1, NS)[0]
    ex = {
        "hot_all":  (top(f), top(s100, 1, NS)[0]),
        "hot100":   (top(f100), hot_s),
        "hot30":    (top(f30), hot_s),
        "cold100":  (top([-v for v in f100]), top([-v for v in s100], 1, NS)[0]),
        "gap":      (top(gap), top(sgap, 1, NS)[0]),
        "due":      (top(due), top(sgap, 1, NS)[0]),
        "ewma":     (top(ew), hot_s),
        "markov":   (top(mk), hot_s),
        "pairs":    (top(pa), hot_s),
        "repeat":   (sorted(last), hot_s),
        "knn":      (top(knn), hot_s),
        "random":   (sorted(rnd.sample(range(1, N + 1), PICK)), rnd.randint(1, NS)),
    }
    return {k: {"nums": v[0], "strong": v[1]} for k, v in ex.items()}


def vote(ex, weights, hist):
    v = [0.0] * (N + 1); sv = [0.0] * (NS + 1)
    f100 = [0] * (N + 1)
    for d in hist[-100:]:
        for x in d["nums"]: f100[x] += 1
    for k, e in ex.items():
        for x in e["nums"]: v[x] += weights[k]
        sv[e["strong"]] += weights[k]
    for x in range(1, N + 1): v[x] += f100[x] * 1e-6
    return top(v), top(sv, 1, NS)[0]


def update(weights, ex, draw):
    for k, e in ex.items():
        h = len(set(e["nums"]) & set(draw["nums"]))
        weights[k] *= math.exp(ETA * (h - E_HITS))
    tot = sum(weights.values())
    for k in weights: weights[k] *= len(weights) / tot


def round_for(hist, weights):
    nxt = hist[-1]["id"] + 1
    ex = experts(hist, nxt * 7919)
    nums, strong = vote(ex, weights, hist)
    return {"draw": nxt, "after": hist[-1]["id"], "registered_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "nums": nums, "strong": strong, "experts": ex, "weights_before": {k: round(v, 4) for k, v in weights.items()}}


def main():
    draws = load_draws()
    by_id = {d["id"]: d for d in draws}
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
    else:
        # warm-up on past draws; these rounds are not part of the record
        names = list(experts(draws[:-WARMUP - 1], 1).keys())
        weights = {k: 1.0 for k in names}
        start = len(draws) - WARMUP
        for i in range(start, len(draws)):
            ex = experts(draws[:i], draws[i]["id"] * 7919)
            update(weights, ex, draws[i])
        st = {"version": 1, "eta": ETA, "warmup_draws": WARMUP, "started_after": draws[-1]["id"],
              "weights": weights, "rounds": [], "next": None}
        print(f"warm-up done on draws {draws[start]['id']}..{draws[-1]['id']}")
    weights = st["weights"]
    changed = False
    # score the registered round(s) whose draw is now known
    while st["next"] and st["next"]["draw"] in by_id:
        r = st["next"]; d = by_id[r["draw"]]
        r["result"] = {"nums": d["nums"], "strong": d["strong"], "date": d["date"]}
        r["hits"] = len(set(r["nums"]) & set(d["nums"])); r["strong_hit"] = r["strong"] == d["strong"]
        r["expert_hits"] = {k: len(set(e["nums"]) & set(d["nums"])) for k, e in r["experts"].items()}
        update(weights, r["experts"], d)
        st["rounds"].append(r)
        print(f"draw {d['id']}: ticket {r['nums']} +{r['strong']} caught {r['hits']}{' + strong' if r['strong_hit'] else ''}")
        hist = [x for x in draws if x["id"] <= d["id"]]
        st["next"] = round_for(hist, weights) if hist[-1]["id"] == draws[-1]["id"] else None
        changed = True
    if not st["next"]:
        st["next"] = round_for(draws, weights); changed = True
    if st["next"]["draw"] != draws[-1]["id"] + 1:
        print("waiting: a newer draw exists than the registered round", file=sys.stderr)
    st["weights"] = {k: round(v, 6) for k, v in weights.items()}
    if changed:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        n = st["next"]; print(f"registered for draw {n['draw']}: {n['nums']} +{n['strong']}")
    else:
        print("nothing new")


if __name__ == "__main__":
    main()
