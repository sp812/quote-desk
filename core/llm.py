"""Thin wrapper over the Claude Messages API.

Notes for current models:
- temperature/top_p must not be set, and forced tool_choice is rejected, so structured output is
  requested by offering one tool and asking the model to call it, with a retry and a JSON fallback.
- Speed vs depth is controlled with output_config.effort (low | medium | high).
- Rate limits (429) and overloads (529) are retried with backoff, honouring retry-after.
"""
from __future__ import annotations
import json
import random
import re
import time
from typing import Any, Callable

from .config import MODEL

RETRYABLE = (408, 409, 429, 500, 502, 503, 504, 529)


def client():
    import anthropic
    return anthropic.Anthropic(max_retries=0, timeout=300)


def _text_of(resp) -> str:
    return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")


def _retry_after(e) -> float | None:
    resp = getattr(e, "response", None)
    headers = getattr(resp, "headers", None) or {}
    try:
        v = headers.get("retry-after")
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _create(effort: str | None = None, **kw):
    c = client()
    if effort:
        kw.setdefault("extra_body", {})["output_config"] = {"effort": effort}
    last = None
    for attempt in range(6):
        try:
            return c.messages.create(**kw)
        except Exception as e:
            last = e
            status = getattr(e, "status_code", None)
            msg = str(e).lower()
            transient = status in RETRYABLE or any(s in msg for s in ("rate", "overloaded", "timeout", "timed out", "connection"))
            if status in (400, 401, 403, 404, 413, 422) or not transient:
                raise
            wait = _retry_after(e) or min(60, 3 * 2 ** attempt)
            time.sleep(wait + random.uniform(0, 1.5))
    raise last


def structured_call(system: str, content: list[dict] | str, tool_name: str, tool_desc: str, schema: dict,
                    model: str = MODEL, max_tokens: int = 32000, effort: str | None = None) -> dict:
    """Ask the model to answer by calling one tool; return the tool input as a dict."""
    tools = [{"name": tool_name, "description": tool_desc, "input_schema": schema}]
    messages = [{"role": "user", "content": content}]
    for _ in range(3):
        resp = _create(effort=effort, model=model, max_tokens=max_tokens, system=system, tools=tools, messages=messages)
        for b in resp.content:
            if getattr(b, "type", "") == "tool_use" and b.name == tool_name:
                return b.input if isinstance(b.input, dict) else _parse_json(b.input) or {}
        parsed = _parse_json(_text_of(resp))
        if parsed:
            return parsed
        messages = messages + [{"role": "assistant", "content": resp.content},
                               {"role": "user", "content": f"Please submit your answer by calling the {tool_name} tool now."}]
    raise RuntimeError(f"The model did not return {tool_name} after 3 attempts.")


def _parse_json(txt) -> dict | None:
    if isinstance(txt, dict):
        return txt
    m = re.search(r"\{.*\}", str(txt or ""), re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        return None


def agent_loop(system: str, messages: list[dict], tools: list[dict], run_tool: Callable[[str, dict], Any],
               on_step: Callable[[dict], None] | None = None, model: str = MODEL, max_steps: int = 10,
               max_tokens: int = 16000, effort: str | None = "medium") -> tuple[str, list[dict]]:
    """Generic tool-use loop. Returns (final_text, updated_messages). Each tool call is reported via on_step."""
    msgs = list(messages)
    for _ in range(max_steps):
        resp = _create(effort=effort, model=model, max_tokens=max_tokens, system=system, tools=tools, messages=msgs)
        msgs.append({"role": "assistant", "content": resp.content})  # keep thinking blocks intact
        uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
        if not uses:
            return _text_of(resp), msgs
        results = []
        for u in uses:
            inp = u.input if isinstance(u.input, dict) else (_parse_json(u.input) or {})
            try:
                out = run_tool(u.name, inp)
                is_err = False
            except Exception as e:
                out, is_err = f"ERROR: {e}", True
            if on_step:
                on_step({"tool": u.name, "input": inp, "output": out, "error": is_err})
            results.append({"type": "tool_result", "tool_use_id": u.id,
                            "content": out if isinstance(out, str) else json.dumps(out, default=str)[:60000],
                            "is_error": is_err})
        msgs.append({"role": "user", "content": results})
    return "I stopped after too many steps. Try a narrower question.", msgs


def simple_text(system: str, prompt: str, model: str = MODEL, max_tokens: int = 8000, effort: str | None = "medium") -> str:
    resp = _create(effort=effort, model=model, max_tokens=max_tokens, system=system,
                   messages=[{"role": "user", "content": prompt}])
    return _text_of(resp)
