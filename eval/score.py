"""Score eval/results/raw_traces.jsonl against eval/questions.jsonl.

Metrics (per system x model, averaged over runs):
  accuracy            in-scope: every required fact present and no refusal;
                      out-of-scope / missing-info: refused (and no invented e-mail address)
  groundedness        among correct in-scope answers, share that cite an expected source document
  oos_refusal         share of out-of-scope + missing-info questions correctly refused
  false_refusal       share of in-scope questions wrongly refused
  routing             multi-agent only: question reached the expected specialist
  logged              refused answers that were written to the unanswered-questions log by the agent itself
  latency             median seconds per question
Also writes the list of questions whose correctness or key facts changed across repeated runs.

Automatic matching is strict string/regex matching; check eval/results/per_question.csv by hand
and put 1/0 in the manual_override column where the matcher is wrong, then re-run this script.

Run:  python eval/score.py
"""
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "eval" / "results"


def norm(s: str) -> str:
    s = (s or "").lower().replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", s)


def group_hit(answer: str, group: list[str]) -> bool:
    a = norm(answer)
    for alt in group:
        if alt.startswith("re:"):
            if re.search(alt[3:], a, re.I):
                return True
        elif alt.lower() in a:
            return True
    return False


def key_facts(answer: str) -> str:
    """Numbers, dates, slot-like tokens and e-mails: used to detect drift between runs."""
    a = norm(answer)
    toks = re.findall(r"[\w.]+@[\w.-]+|\b\d+(?:[.,]\d+)*\b|\bslot\s*[a-z]\d*\b", a)
    return " ".join(sorted(set(toks)))


def score_one(q: dict, t: dict) -> dict:
    ans, refused = t.get("answer", ""), t.get("refused", False)
    hits = [group_hit(ans, g) for g in q["must_include"]]
    cites = [s for s in q["sources"] if s.lower() in norm(ans)]
    cites_any = bool(re.search(r"source|\bp\. ?\d|section|according to|as per", ans, re.I))
    if q["type"] == "in_scope":
        correct = all(hits) and not refused and bool(ans)
    elif q["must_include"]:  # missing_info with an expected explanation (e.g. unknown course code)
        correct = (all(hits) or refused) and "@iitj-dummy" not in ans
    else:
        correct = refused
    tools = [c["tool"] for c in t.get("tool_calls", [])]
    return {
        "correct": int(correct),
        "partial": round(sum(hits) / len(hits), 2) if hits else (1.0 if correct else 0.0),
        "grounded": int(bool(cites)) if q["type"] == "in_scope" and correct else "",
        "cites_any": int(cites_any),
        "refused": int(refused),
        "routed_ok": int(q["expected_agent"] in (t.get("agents") or [])) if t["system"] == "multi" else "",
        "agent_logged": int("log_unanswered_question" in tools) if refused else "",
        "tools": " ".join(tools),
        "facts": key_facts(ans),
    }


def main():
    questions = {q["id"]: q for q in map(json.loads, (ROOT / "eval/questions.jsonl").read_text(encoding="utf-8").splitlines())}
    raw_path = RES / "raw_traces.jsonl"
    if not raw_path.exists():
        sys.exit("No traces yet. Run eval/run_eval.py first.")
    traces = [json.loads(l) for l in raw_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    overrides = {}
    pq_path = RES / "per_question.csv"
    if pq_path.exists():
        for r in csv.DictReader(pq_path.open(encoding="utf-8")):
            if r.get("manual_override", "").strip() in ("0", "1"):
                overrides[(r["system"], r["model"], r["run"], r["id"])] = int(r["manual_override"])

    rows = []
    for t in traces:
        q = questions.get(t["id"])
        if not q:
            continue
        s = score_one(q, t)
        k = (t["system"], t["model"], str(t["run"]), t["id"])
        if k in overrides:
            s["correct"] = overrides[k]
        rows.append({"system": t["system"], "model": t["model"], "run": t["run"], "id": t["id"],
                     "category": q["category"], "type": q["type"], **s,
                     "manual_override": overrides.get(k, ""), "latency_s": t.get("latency_s"),
                     "error": t.get("error") or "", "agents": " -> ".join(t.get("agents") or []),
                     "answer": t.get("answer", "").replace("\n", " ")[:600]})

    with pq_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- aggregate
    by = defaultdict(list)
    for r in rows:
        by[(r["system"], r["model"])].append(r)

    def pct(xs):
        xs = [x for x in xs if x != ""]
        return f"{100 * sum(xs) / len(xs):.0f}% ({sum(xs)}/{len(xs)})" if xs else "-"

    lines = ["# Evaluation summary", "",
             "| System | Model | Runs | Accuracy | Groundedness | OOS refusal | False refusal | Routing | Agent logged refusals | Median latency (s) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for (system, model), rs in sorted(by.items()):
        ins = [r for r in rs if r["type"] == "in_scope"]
        oos = [r for r in rs if r["type"] != "in_scope"]
        lat = [r["latency_s"] for r in rs if r["latency_s"] is not None]
        lines.append(f"| {system} | {model} | {len({r['run'] for r in rs})} | {pct([r['correct'] for r in rs])} | "
                     f"{pct([r['grounded'] for r in ins])} | {pct([r['correct'] for r in oos])} | "
                     f"{pct([r['refused'] for r in ins])} | {pct([r['routed_ok'] for r in rs])} | "
                     f"{pct([r['agent_logged'] for r in rs])} | {statistics.median(lat) if lat else '-'} |")

    lines += ["", "## Accuracy by category", "", "| System | Model | " + " | ".join(
        c for c in ("policy", "schedule", "email", "oos")) + " |", "|---|---|---|---|---|---|"]
    for (system, model), rs in sorted(by.items()):
        cells = [pct([r["correct"] for r in rs if r["category"] == c]) for c in ("policy", "schedule", "email", "oos")]
        lines.append(f"| {system} | {model} | " + " | ".join(cells) + " |")

    # ---- consistency across runs
    groups = defaultdict(list)
    for r in rows:
        groups[(r["system"], r["model"], r["id"])].append(r)
    unstable = []
    for (system, model, qid), rs in sorted(groups.items()):
        if len(rs) < 2:
            continue
        corr = {r["correct"] for r in rs}
        facts = {r["facts"] for r in rs}
        if len(corr) > 1 or len(facts) > 1:
            unstable.append({"system": system, "model": model, "id": qid, "question": questions[qid]["question"],
                             "correct_per_run": " ".join(str(r["correct"]) for r in sorted(rs, key=lambda x: x["run"])),
                             "changed": "correctness" if len(corr) > 1 else "wording/facts only",
                             "answers": " ||| ".join(r["answer"][:200] for r in sorted(rs, key=lambda x: x["run"]))})
    if unstable:
        with (RES / "unstable_questions.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(unstable[0].keys()))
            w.writeheader()
            w.writerows(unstable)
    lines += ["", "## Questions whose answers changed across runs", "",
              "| System | Model | Question | Correct per run | Change |", "|---|---|---|---|---|"]
    lines += [f"| {u['system']} | {u['model']} | {u['id']} | {u['correct_per_run']} | {u['changed']} |" for u in unstable]
    (RES / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {RES.relative_to(ROOT)}/summary.md, per_question.csv, unstable_questions.csv")


if __name__ == "__main__":
    main()
