# Entry point for `adk web` / `adk run helpdesk_single`
from helpdesk.agents import build_single_agent

root_agent = build_single_agent()
