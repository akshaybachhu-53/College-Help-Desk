"""Running a question through an ADK agent and collecting a trace (tools, agents, timing)."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from helpdesk import config

APP = "iitj_academic_helpdesk"
REFUSAL_RE = re.compile(r"\b(i don'?t know|i do not know|not able to answer|cannot answer|can't answer|"
                        r"outside (my|the) scope|have logged your question|can'?t help|cannot help|unable to (help|answer|find))\b", re.I)
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def clean_text(text: str) -> str:
    return THINK_RE.sub("", text or "").strip()


def is_refusal(text: str) -> bool:
    return bool(REFUSAL_RE.search(text or ""))


class HelpdeskSession:
    """One conversation (keeps history between turns). Use a new one per evaluation question."""

    def __init__(self, agent, user_id: str = "student"):
        self.agent, self.user_id = agent, user_id
        self.sessions = InMemorySessionService()
        self.runner = Runner(agent=agent, app_name=APP, session_service=self.sessions)
        self.session_id = None

    async def ask(self, question: str, timeout_s: int = 300) -> dict:
        if self.session_id is None:
            s = await self.sessions.create_session(app_name=APP, user_id=self.user_id, session_id=str(uuid.uuid4()))
            self.session_id = s.id
        trace = {"question": question, "tool_calls": [], "agents": [], "answer": "", "error": None}
        msg = types.Content(role="user", parts=[types.Part(text=question)])
        t0 = time.perf_counter()

        async def _consume():
            async for ev in self.runner.run_async(user_id=self.user_id, session_id=self.session_id,
                                                  new_message=msg, run_config=RunConfig(max_llm_calls=15)):
                if ev.author and ev.author != "user" and (not trace["agents"] or trace["agents"][-1] != ev.author):
                    trace["agents"].append(ev.author)
                for fc in ev.get_function_calls() or []:
                    trace["tool_calls"].append({"agent": ev.author, "tool": fc.name, "args": dict(fc.args or {})})
                for fr in ev.get_function_responses() or []:
                    resp = fr.response or {}
                    for call in reversed(trace["tool_calls"]):
                        if call["tool"] == fr.name and "result" not in call:
                            call["result"] = json.dumps(resp, ensure_ascii=False, default=str)[:1500]
                            break
                if ev.content and ev.content.parts and not ev.partial:
                    # Qwen3's reasoning arrives as parts flagged thought=True; keep it out of the answer
                    thoughts = "".join(p.text or "" for p in ev.content.parts if getattr(p, "thought", False))
                    txt = "".join(p.text or "" for p in ev.content.parts
                                  if getattr(p, "text", None) and not getattr(p, "thought", False))
                    if thoughts.strip():
                        trace["reasoning"] = (trace.get("reasoning", "") + "\n" + thoughts)[-4000:]
                    if txt.strip():
                        trace["answer"] = txt  # last non-empty model text wins

        try:
            await asyncio.wait_for(_consume(), timeout=timeout_s)
        except asyncio.TimeoutError:
            trace["error"] = f"timeout after {timeout_s}s"
        except Exception as e:  # keep the evaluation going; record the failure
            trace["error"] = f"{type(e).__name__}: {e}"[:500]
        trace["answer"] = clean_text(trace["answer"])
        trace["latency_s"] = round(time.perf_counter() - t0, 2)
        trace["refused"] = is_refusal(trace["answer"])
        trace["final_agent"] = trace["agents"][-1] if trace["agents"] else None

        # Safety net for the human-referral log: small models sometimes say "I don't know"
        # without calling the logging tool. Record those too, marked as logged by the runner.
        if (trace["refused"] or not trace["answer"]) and not any(c["tool"] == "log_unanswered_question"
                                                                 for c in trace["tool_calls"]):
            config.LOG_DIR.mkdir(parents=True, exist_ok=True)
            with config.UNANSWERED_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "question": question,
                                    "reason": "no_answer" if not trace["answer"] else "refused",
                                    "logged_by": "runner"}, ensure_ascii=False) + "\n")
        return trace


async def ask_once(agent, question: str, timeout_s: int = 300) -> dict:
    return await HelpdeskSession(agent).ask(question, timeout_s)
