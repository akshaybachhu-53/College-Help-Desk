"""Run the question set through the helpdesk and save raw traces.

  python eval/run_eval.py --system multi --models helpdesk-qwen3:8b --runs 3
  python eval/run_eval.py --system single multi --models helpdesk-qwen3:8b helpdesk-llama3.1:8b --runs 3

Each (system, model, run) gets a fresh session per question. Output is appended to
eval/results/raw_traces.jsonl, so an interrupted run can be resumed (finished items are skipped).
"""
import argparse
import asyncio
import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
os.environ.setdefault("LITELLM_LOG", "ERROR")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpdesk.agents import build_multi_agent, build_single_agent  # noqa: E402
from helpdesk.runner import ask_once  # noqa: E402

OUT = ROOT / "eval" / "results" / "raw_traces.jsonl"


def done_keys() -> set:
    if not OUT.exists():
        return set()
    keys = set()
    for line in OUT.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        keys.add((r["system"], r["model"], r["run"], r["id"]))
    return keys


async def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", nargs="+", default=["multi"], choices=["multi", "single"])
    ap.add_argument("--models", nargs="+", default=[os.getenv("HELPDESK_MODEL", "helpdesk-qwen3:8b")])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--ids", nargs="*", help="only these question ids, e.g. Q01 Q13")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--out", default=str(OUT), help="traces file (default eval/results/raw_traces.jsonl)")
    a = ap.parse_args()
    OUT = Path(a.out)

    questions = [json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()]
    if a.ids:
        questions = [q for q in questions if q["id"] in a.ids]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    skip = done_keys()

    for system in a.system:
        for model in a.models:
            agent = (build_multi_agent if system == "multi" else build_single_agent)(model)
            for run in range(1, a.runs + 1):
                for q in questions:
                    key = (system, model, run, q["id"])
                    if key in skip:
                        continue
                    t = await ask_once(agent, q["question"], a.timeout)
                    rec = {"system": system, "model": model, "run": run, "id": q["id"], **t}
                    with OUT.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    flag = "ERR" if t["error"] else ("REF" if t["refused"] else "ok ")
                    print(f"[{system}|{model}|run {run}] {q['id']} {flag} {t['latency_s']:6.1f}s  "
                          f"{' -> '.join(t['agents'])}  | {t['answer'][:90]!r}", flush=True)
    print(f"\nTraces in {OUT}. Now run: python eval/score.py")


if __name__ == "__main__":
    asyncio.run(main())
