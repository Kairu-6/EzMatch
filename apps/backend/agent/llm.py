"""
agent/llm.py
============
The model interface, abstracted so the agent loop is identical whether the
high-end Morpheus model supports native OpenAI tool-calling or not.

  - NATIVE mode: pass `tools=[...]`, read `message.tool_calls`.
  - ReAct mode:  describe the tools in the prompt, ask for a JSON action
                 `{"thought","tool","args"}` / `{"thought","final":true}`,
                 and synthesize a tool call so the loop dispatches identically.

Mode is chosen once via a startup probe (or forced with MORPHEUS_AGENT_TOOLS).
ReAct is the safe default if the probe is inconclusive — many OpenAI-compatible
gateways accept the `tools` param but never actually emit tool calls.
"""
import json
import logging
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from openai import OpenAI

# Reuse the proven SDK setup + fence stripper from the document parser.
from parser_llm import _strip_fences

load_dotenv()
logger = logging.getLogger(__name__)

MORPHEUS_URL     = os.getenv("MORPHEUS_URL")
MORPHEUS_API_KEY = os.getenv("MORPHEUS_API_KEY")
# The high-end agent model. Default = the confirmed-working text model on this
# account; qwen kept as the documented fallback. One swappable env var.
AGENT_MODEL      = os.getenv("MORPHEUS_AGENT_MODEL", "llama-3.3-70b")
TOOLS_MODE_ENV   = os.getenv("MORPHEUS_AGENT_TOOLS", "auto").lower()   # auto | native | react
CALL_TIMEOUT     = float(os.getenv("AGENT_LLM_TIMEOUT", "120"))
TEMPERATURE      = float(os.getenv("AGENT_TEMPERATURE", "0.0"))

_client = OpenAI(base_url=MORPHEUS_URL, api_key=MORPHEUS_API_KEY)
_MODE: str | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class StepResult:
    assistant_message: dict          # appended verbatim to working memory
    text: str | None                 # the model's visible reasoning, if any
    tool_calls: list[ToolCall] = field(default_factory=list)
    parse_error: bool = False        # ReAct: model didn't emit valid JSON


# ── mode selection ────────────────────────────────────────────────
def get_mode() -> str:
    global _MODE
    if _MODE:
        return _MODE
    if TOOLS_MODE_ENV in ("native", "react"):
        _MODE = TOOLS_MODE_ENV
    else:
        _MODE = _probe_native()
    logger.info("Agent tool-calling mode: %s (model=%s)", _MODE, AGENT_MODEL)
    return _MODE


def _probe_native() -> str:
    """Force a trivial tool call; if the gateway returns one, native works."""
    ping = {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "Reply by calling this tool.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
    try:
        resp = _client.chat.completions.create(
            model=AGENT_MODEL,
            messages=[{"role": "user", "content": "Call the ping tool."}],
            tools=[ping],
            tool_choice={"type": "function", "function": {"name": "ping"}},
            temperature=0.0,
            timeout=CALL_TIMEOUT,
        )
        if resp.choices[0].message.tool_calls:
            return "native"
        logger.info("Probe: gateway accepted tools but emitted none -> ReAct.")
        return "react"
    except Exception as exc:
        logger.info("Probe: native tool-calling unavailable (%s) -> ReAct.", exc)
        return "react"


# ── the single step() the loop calls ──────────────────────────────
def step(messages: list[dict], tools_param: list[dict] | None) -> StepResult:
    return _step_native(messages, tools_param) if get_mode() == "native" \
        else _step_react(messages)


def _step_native(messages: list[dict], tools_param: list[dict] | None) -> StepResult:
    resp = _client.chat.completions.create(
        model=AGENT_MODEL,
        messages=messages,
        tools=tools_param,
        tool_choice="auto",
        temperature=TEMPERATURE,
        timeout=CALL_TIMEOUT,
    )
    msg = resp.choices[0].message
    calls: list[ToolCall] = []
    assistant_message: dict = {"role": "assistant", "content": msg.content}
    if msg.tool_calls:
        assistant_message["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))
    return StepResult(assistant_message=assistant_message, text=msg.content, tool_calls=calls)


def _step_react(messages: list[dict]) -> StepResult:
    resp = _client.chat.completions.create(
        model=AGENT_MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        timeout=CALL_TIMEOUT,
    )
    raw = resp.choices[0].message.content or ""
    assistant_message = {"role": "assistant", "content": raw}

    try:
        obj = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        return StepResult(assistant_message, text=raw, tool_calls=[], parse_error=True)

    if not isinstance(obj, dict):
        return StepResult(assistant_message, text=raw, tool_calls=[], parse_error=True)

    thought = obj.get("thought")
    calls: list[ToolCall] = []

    if obj.get("final") or obj.get("tool") == "finish":
        args = dict(obj.get("args") or {})
        if "summary" not in args:
            args["summary"] = obj.get("summary") or thought or "Done."
        calls.append(ToolCall(id="finish", name="finish", args=args))
    elif obj.get("tool"):
        args = obj.get("args") or obj.get("arguments") or {}
        calls.append(ToolCall(id=f"react_{obj['tool']}", name=obj["tool"],
                              args=args if isinstance(args, dict) else {}))

    return StepResult(assistant_message, text=thought, tool_calls=calls)


def tool_result_message(tool_call: ToolCall, result: dict) -> dict:
    """Format a tool's return value as the next message, per mode."""
    content = json.dumps(result, default=str)
    if get_mode() == "native":
        return {"role": "tool", "tool_call_id": tool_call.id, "content": content}
    return {"role": "user", "content": f"Observation from {tool_call.name}: {content}"}
