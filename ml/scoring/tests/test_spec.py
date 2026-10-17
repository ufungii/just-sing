"""An independent implementation written ONLY from ml/scoring/SPEC.md (plain
Python, no numpy, no imports from ml.scoring), checked against the shared
fixtures. If this passes, the spec is complete enough to port. It is also a
line-by-line template for the TypeScript version."""
import json
import math
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"
CFG = dict(full_c=70, zero_c=200, tol_s=0.0, full_s=0.10, zero_s=0.40, window_s=0.50,
           L=4, stable_c=60, gap_s=0.12, pw=0.8, tw=0.2, perfect=82, great=65, okay=50, min_cov=0.25)


def voiced(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def median(vals):
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def onsets(track, hop):
    n, L = len(track), CFG["L"]
    stable = [False] * n
    for i in range(n - L + 1):
        w = track[i:i + L]
        if all(voiced(v) for v in w):
            med = median(w)
            stable[i] = max(abs(1200 * math.log2(v / med)) for v in w) <= CFG["stable_c"]
    gap, out = round(CFG["gap_s"] / hop), []
    for i in range(n):
        if stable[i] and (i == 0 or not stable[i - 1]) and (not out or i - out[-1] >= gap):
            out.append(i)
    return [i * hop for i in out]


def score(inp):
    hop, ref, user = inp["hop_seconds"], inp["ref_hz"], inp["user_hz"]
    n = round(inp["latency_offset_s"] / hop)
    if n > 0:
        user = user[n:] + [None] * n
    k = round(inp["time_tolerance_s"] / hop)
    ext = (user + [None] * (len(ref) + k))[:len(ref) + k]   # k extra frames so a shift can reach a late take's tail

    mask = [voiced(v) for v in ref]
    for s, e in inp["excluded"]:
        for i in range(max(0, round(s / hop)), min(len(ref), max(0, round(e / hop)))):
            mask[i] = False
    target = [v * 2 ** (inp["register"] / 12) if voiced(v) else None for v in ref]
    # credit and voicing at every candidate shift of the user's track (in frames)
    per_off = {}
    for off in range(-k, k + 1):
        credit, uv = [0.0] * len(ref), [False] * len(ref)
        for i in range(len(ref)):
            j = i + off
            u = ext[j] if 0 <= j < len(ext) else None
            if voiced(u):
                uv[i] = True
                if mask[i]:
                    err = 1200 * math.log2(u / target[i])
                    credit[i] = clamp((CFG["zero_c"] - abs(err)) / (CFG["zero_c"] - CFG["full_c"]), 0, 1)
        per_off[off] = (credit, uv)

    ref_on = [t for t in inp["ref_onsets"] if not any(s <= t < e for s, e in inp["excluded"])]
    user_on = onsets(user, hop)

    phrases, weights = [], []
    for pid, start, end in inp["phrases"]:
        idx = [i for i in range(round(start / hop), round(end / hop)) if 0 <= i < len(ref) and mask[i]]
        sc = len(idx)
        # ONE shift per phrase: the one with the most credit; ties keep the smallest |shift|
        best = None
        for off in sorted(range(-k, k + 1), key=lambda o: (abs(o), o)):
            total = sum(per_off[off][0][i] for i in idx)
            if best is None or total > best[0]:
                best = (total, off)
        credit, uv = per_off[best[1]]
        pitch = 100 * best[0] / sc if sc else 0.0
        cov = sum(uv[i] for i in idx) / sc if sc else 0.0

        rs = sorted(t for t in ref_on if start <= t < end)
        used, csum = [False] * len(user_on), 0.0
        for r in rs:
            best = None
            for j, u in enumerate(user_on):
                if not used[j] and (best is None or abs(u - r) < abs(user_on[best] - r)):
                    best = j
            if best is None or abs(user_on[best] - r) > CFG["window_s"]:
                continue
            used[best] = True
            d = user_on[best] - r
            csum += clamp((CFG["zero_s"] - abs(d)) / (CFG["zero_s"] - CFG["full_s"]), 0, 1)
        timing = 100 * csum / len(rs) if rs else None

        s = CFG["pw"] * pitch + CFG["tw"] * timing if timing is not None else pitch
        rating = ("miss" if cov < CFG["min_cov"] else "perfect" if s >= CFG["perfect"]
                  else "great" if s >= CFG["great"] else "okay" if s >= CFG["okay"] else "bad")
        phrases.append({"phrase_id": pid, "pitch": round(pitch, 1),
                        "timing": None if timing is None else round(timing, 1),
                        "score": round(s, 1), "coverage": round(cov, 3), "rating": rating})
        weights.append(sc)

    def wmean(key):
        pairs = [(p[key], w) for p, w in zip(phrases, weights) if p[key] is not None and w > 0]
        tw = sum(w for _, w in pairs)
        return round(sum(v * w for v, w in pairs) / tw, 1) if tw else 0.0

    return {"total": wmean("score"), "pitch": wmean("pitch"), "timing": wmean("timing"), "phrases": phrases}


def _load(name):
    path = FIXTURES / name
    if not path.exists():
        pytest.skip("fixtures not generated")
    return json.loads(path.read_text())


def test_spec_implementation_matches_score_fixtures():
    data = _load("score_cases.json")
    tol = data["tolerance"]
    for case in data["cases"]:
        got, exp = score(case["input"]), case["expected"]
        for key in ("total", "pitch", "timing"):
            assert abs(got[key] - exp[key]) <= tol, (case["name"], key, got[key], exp[key])
        for g, e in zip(got["phrases"], exp["phrases"]):
            assert g["rating"] == e["rating"], (case["name"], g, e)
            for key in ("pitch", "timing", "score", "coverage"):
                if e[key] is None:
                    assert g[key] is None
                else:
                    assert abs(g[key] - e[key]) <= tol, (case["name"], key, g, e)


def test_spec_implementation_matches_onset_fixtures():
    data = _load("onset_cases.json")
    for case in data["cases"]:
        got = onsets(case["input"]["hz"], case["input"]["hop_seconds"])
        exp = case["expected_onsets"]
        assert len(got) == len(exp), case["name"]
        assert all(abs(a - b) <= data["tolerance_s"] for a, b in zip(got, exp)), case["name"]
