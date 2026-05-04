"""Quick diagnostic for the most recent benchmark run.

Usage:
    python scripts/bench_diag.py                  # latest run
    python scripts/bench_diag.py benchmark_XYZ    # specific run id
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = Path("e:/Research Project/Code/idpo-data/runs/benchmarks")


def _latest() -> Path:
    dirs = sorted(
        (d for d in BENCH_DIR.iterdir() if d.is_dir() and (d / "paper_evidence.json").exists()),
        key=lambda d: d.stat().st_mtime,
    )
    if not dirs:
        sys.exit("No benchmark runs found")
    return dirs[-1]


def _norm(v: object) -> str:
    import re
    t = " ".join(str(v or "").strip().lower().split())
    return re.sub(r"\s*([/\-,.])\s*", r"\1", t)


def main() -> None:
    if len(sys.argv) > 1:
        run_dir = BENCH_DIR / sys.argv[1]
    else:
        run_dir = _latest()

    ev = json.loads((run_dir / "paper_evidence.json").read_text(encoding="utf-8"))
    docs = ev.get("documents", [])
    conditions = ["static", "adaptive_safe"]

    print(f"Run: {run_dir.name}  ({len(docs)} docs)\n")

    all_ok = True
    for d in docs:
        cid = d["case_id"]
        exp = d.get("expected") or {}
        print(f"-- {cid}")
        if exp:
            print(f"   expected : {exp}")
        else:
            print(f"   expected : (none)")

        for cond in conditions:
            cd = d.get(cond) or {}
            doc = cd.get("doc") or {}
            em = cd.get("exact_metrics") or {}
            f1 = em.get("f1", 0.0)

            # extracted field values
            extracted = {
                k.replace("field_", ""): v
                for k, v in doc.items()
                if k.startswith("field_") and not k.endswith(("_confidence", "_page", "_span", "_source"))
                and v and v != "N/A"
            }

            # LLM outcome
            llm = doc.get("llm_diagnostics") or {}
            lc = llm.get("local_call") or {}
            done = lc.get("done_reason", "?")
            err = lc.get("error", "")
            n_ent = lc.get("entity_count", 0)
            policy = doc.get("policy_id", "?")
            latency = int(doc.get("latency_ms", 0) or 0)

            status = "OK" if f1 > 0 else "XX"
            llm_status = f"done={done}" if not err else f"ERR={err}"
            print(f"   [{cond[:8]}] {status} F1={f1:.3f}  policy={policy}  ents={n_ent}  {llm_status}  {latency}ms")
            if extracted:
                print(f"             got: {extracted}")

            # Per-field match detail when expected exists
            if exp and f1 < 1.0:
                import difflib, re as _re
                def _norm_t(v):
                    t = " ".join(str(v or "").strip().lower().split())
                    t = _re.sub(r"\s*([/\-,.])\s*", r"\1", t)
                    t = _re.sub(r"(\d)[,.](\d)", r"\1,\2", t)
                    t = _re.sub(r"([a-z])(\d)", r"\1 \2", t)
                    t = _re.sub(r"(\d)([a-z])", r"\1 \2", t)
                    t = " ".join(t.split())
                    t = _re.sub(r"(?<=[a-z])\.(?=[a-z])", "", t)
                    return t
                _NUM_HINTS = ("amount","price","total","subtotal","tax","cash","change")
                def _num_norm(k, v):
                    import re as _r
                    t = " ".join(str(v or "").strip().lower().split())
                    t = _r.sub(r"\s*([/\-,.])\s*", r"\1", t)
                    if any(h in k.lower() for h in _NUM_HINTS):
                        t = _r.sub(r"^[^\d\-\.]+", "", t).strip() or t
                        t = t.replace(",","")
                        if t.count(".")==1:
                            i,f = t.split(".")
                            t = i+f if len(f)==3 else (i if not f.rstrip("0") else f"{i}.{f.rstrip('0')}")
                    return t
                for key, ev_val in exp.items():
                    got_raw = extracted.get(key, "")
                    is_num = any(h in key.lower() for h in _NUM_HINTS)
                    e_norm = _num_norm(key, ev_val)
                    g_norm = _num_norm(key, got_raw)
                    sim = difflib.SequenceMatcher(None, _norm_t(got_raw), _norm_t(ev_val)).ratio()
                    if g_norm and g_norm == e_norm:
                        match = "OK"
                    elif is_num:
                        match = "XX"  # numeric: exact only, no fuzzy
                    elif g_norm and sim >= 0.75:
                        match = f"~~ sim={sim:.2f}"
                    else:
                        match = f"XX sim={sim:.2f}"
                    print(f"             {match} {key}: exp={repr(e_norm)}  got={repr(g_norm)}")
            if f1 < 1.0:
                all_ok = False
        print()

    # Summary table
    print("-- SUMMARY --")
    comp = ev.get("comparison") or {}
    print(f"  wins={comp.get('exact_win_count',0)}  ties={comp.get('exact_match_count',0)}  losses={comp.get('exact_loss_count',0)}")
    comp = ev.get("comparison") or {}
    for cond in conditions:
        cd = comp.get(cond) or {}
        efm = cd.get("exact_field_metrics") or {}
        latency = int(cd.get("avg_latency_ms") or 0)
        accepted = cd.get("advice_accepted_count", 0)
        total = cd.get("doc_count", 0)
        f1 = efm.get("f1", 0.0)
        tp, fp, fn = efm.get("tp",0), efm.get("fp",0), efm.get("fn",0)
        print(f"  {cond[:14]:14s}  F1={f1:.3f} (tp={tp} fp={fp} fn={fn})  latency={latency}ms  accepted={accepted}/{total}")
    print()
    if all_ok:
        print("All docs F1=1.0")


if __name__ == "__main__":
    main()
