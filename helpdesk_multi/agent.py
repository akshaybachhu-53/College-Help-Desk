# Entry point for `adk web` / `adk run helpdesk_multi`
from helpdesk.agents import build_multi_agent

root_agent = build_multi_agent()
