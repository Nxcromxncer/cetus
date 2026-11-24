"""The brain: LLM + agent loop (think -> act -> observe -> repeat).

- Multiple providers (Groq, OpenRouter, Ollama) with retry + automatic fallback.
- Guards for models that claim actions they never took, or print fake tool calls.
"""
import json, re, time
from typing import Callable
import requests
import config
from core import registry, safety, context

CLAIM = re.compile(r"\b(installed|opened|launched|closed|started|applied|executed|played|muted|unmuted)\b", re.I)
NUDGE = ("System notice: you did not call any tool, so nothing was actually done. Never claim an action happened "
         "without a tool result. Either call one of the available tools now, or tell the user honestly that you can't do it.")
GIVE_UP = "I haven't actually done that, so nothing was changed. Could you rephrase or ask for one thing at a time?"
RETRYABLE = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_WAIT = 8      # seconds; a longer Retry-After usually means a daily limit, so switch provider instead


def _text_tool_call(content: str):
    """Some models print a tool call as JSON text. Parse it if valid."""
    if not content.startswith("{"):
        return None
    try:
        d = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(d, dict) and "name" in d:
        return d["name"], (d.get("parameters") or d.get("arguments") or {})
    return None


def _looks_like_tool_json(content: str) -> bool:
    return content.startswith("{") and '"name"' in content


def _parse_calls(raw) -> list[dict]:
    out = []
    for i, c in enumerate(raw or []):
        fn = c.get("function", {})
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except json.JSONDecodeError:
                args = {}
        out.append({"id": c.get("id") or f"call_{i}", "name": fn.get("name", ""),
                    "args": args if isinstance(args, dict) else {}})
    return out


class Brain:
    def __init__(self, confirm: Callable[[str], bool], on_event: Callable[[str], None] = print):
        self.confirm = confirm
        self.on_event = on_event
        self.history: list[dict] = []     # plain user/assistant turns only

    # ---------- LLM call with retry + fallback ----------
    def _chat(self, messages, tools):
        providers = config.active_providers()
        if not providers:
            raise RuntimeError("No LLM provider configured. Put GROQ_API_KEY in .env (see .env.example).")
        last = "unknown error"
        for name, p in providers:
            for attempt in range(2):
                try:
                    r = requests.post(
                        f"{p['base_url']}/chat/completions",
                        headers={"Authorization": f"Bearer {p['key']}"},
                        json={"model": p["model"], "messages": messages, "tools": tools, "temperature": 0.1},
                        timeout=60)
                except requests.RequestException as e:
                    last = f"{name}: {type(e).__name__}"
                    break                                             # next provider
                if r.ok:
                    return r.json()["choices"][0]["message"]
                body = r.text[:300]
                last = f"{name}: HTTP {r.status_code} {body}"
                retry = r.status_code in RETRYABLE or (r.status_code == 400 and "tool_use_failed" in body)
                if not retry or attempt == 1:
                    break
                try:
                    wait = float(r.headers.get("retry-after") or 1)
                except ValueError:
                    wait = 1
                if wait > MAX_WAIT:
                    break
                time.sleep(wait)
            self.on_event(f"  [provider] {name} failed ({last[:120]}), trying next")
        raise RuntimeError(f"all providers failed. Last error: {last}")

    # ---------- safe tool execution ----------
    def _execute(self, name: str, args: dict) -> dict:
        t = registry.TOOLS.get(name)
        if not t:
            return {"error": f"unknown tool '{name}'. Available: {', '.join(registry.TOOLS)}"}
        decision = safety.check(t, args)
        if decision == "deny":
            result = {"error": "blocked by safety policy"}
        elif decision == "confirm" and not self.confirm(f"Run {name}({args})?"):
            result = {"error": "user declined"}
        else:
            result = registry.call(name, args)
        safety.log_action(name, args, decision, result)
        return result

    # ---------- the agent loop ----------
    def run(self, user_text: str) -> str:
        tools = [t.spec() for t in registry.TOOLS.values()]
        messages = [{"role": "system", "content": context.build_system_prompt()},
                    *self.history[-config.HISTORY_TURNS * 2:],
                    {"role": "user", "content": user_text}]
        final, used_tool, nudged = "Sorry, I couldn't finish that.", False, False

        for _ in range(config.MAX_STEPS):
            msg = self._chat(messages, tools)
            content = (msg.get("content") or "").strip()
            calls = _parse_calls(msg.get("tool_calls"))

            if not calls:
                parsed = _text_tool_call(content)
                if parsed and parsed[0] in registry.TOOLS:       # valid JSON tool call printed as text
                    calls = [{"id": "text_call", "name": parsed[0],
                              "args": parsed[1] if isinstance(parsed[1], dict) else {}}]
                    content = ""

            if not calls:
                bad = _looks_like_tool_json(content) or (not used_tool and bool(CLAIM.search(content)))
                if bad and not nudged:
                    nudged = True
                    messages += [{"role": "assistant", "content": content or "(no reply)"},
                                 {"role": "user", "content": NUDGE}]
                    continue
                final = GIVE_UP if bad else (content or "Done.")
                break

            messages.append({"role": "assistant", "content": content, "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for c in calls]})
            for c in calls:
                used_tool = True
                self.on_event(f"  [tool] {c['name']}({c['args']})")
                result = self._execute(c["name"], c["args"])
                self.on_event(f"  [result] {result}")
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(result)})

        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": final}]
        return final
