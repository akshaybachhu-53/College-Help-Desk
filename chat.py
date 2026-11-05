"""Interactive helpdesk in the terminal.

  python chat.py                      # multi-agent, default model
  python chat.py --system single      # single-agent baseline
  python chat.py --model helpdesk-llama3.1:8b --trace
"""
import argparse
import asyncio
import os
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("LITELLM_LOG", "ERROR")

from helpdesk.agents import build_multi_agent, build_single_agent  # noqa: E402
from helpdesk.runner import HelpdeskSession  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["multi", "single"], default="multi")
    ap.add_argument("--model", default=None, help="Ollama model tag (default from HELPDESK_MODEL)")
    ap.add_argument("--trace", action="store_true", help="print agents and tool calls")
    a = ap.parse_args()
    agent = (build_multi_agent if a.system == "multi" else build_single_agent)(a.model)
    sess = HelpdeskSession(agent)
    print(f"IIT Jodhpur Academic Helpdesk ({a.system}-agent). Type 'exit' to quit.\n")
    while True:
        try:
            q = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit"):
            break
        if not q:
            continue
        t = await sess.ask(q)
        if a.trace:
            print(f"  [agents: {' -> '.join(t['agents'])}]")
            for c in t["tool_calls"]:
                print(f"  [tool: {c['tool']}({c['args']})]")
            print(f"  [{t['latency_s']} s]")
        print(f"\nHelpdesk: {t['answer'] or '(no answer: ' + str(t['error']) + ')'}\n")


if __name__ == "__main__":
    asyncio.run(main())
