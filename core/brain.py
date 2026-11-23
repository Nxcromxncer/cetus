"""The brain: LLM + agent loop (think -> act -> observe -> repeat)."""
import json
from typing import Callable
import requests
import config
from core import registry, safety, context


class Brain:
    def __init__(self, confirm: Callable[[str], bool], on_event: Callable[[str], None] = print):
        self.confirm = confirm
        self.on_event = on_event
        self.history: list[dict] = []     # plain user/assistant turns only

    def _chat(self, messages, tools):
        r = requests.post(
            f"{config.BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.API_KEY}"},
            json={"model": config.MODEL, "messages": messages, "tools": tools, "temperature": 0.1},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]

    def _execute(self, name: str, args: dict) -> dict:
        t = registry.TOOLS.get(name)
        if not t:
            return {"error": f"unknown tool '{name}'"}
        decision = safety.check(t, args)
        if decision == "deny":
            result = {"error": "blocked by safety policy"}
        elif decision == "confirm" and not self.confirm(f"Run {name}({args})?"):
            result = {"error": "user declined"}
        else:
            result = registry.call(name, args)
        safety.log_action(name, args, decision, result)
        return result

    def run(self, user_text: str) -> str:
        tools = [t.spec() for t in registry.TOOLS.values()]
        messages = [{"role": "system", "content": context.build_system_prompt()},
                    *self.history[-config.HISTORY_TURNS * 2:],
                    {"role": "user", "content": user_text}]
        final = "Sorry, I couldn't finish that."
        for _ in range(config.MAX_STEPS):
            msg = self._chat(messages, tools)
            messages.append(msg)
            calls = msg.get("tool_calls")
            if not calls:
                final = (msg.get("content") or "").strip() or "Done."
                break
            for i, c in enumerate(calls):
                fn = c["function"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args or "{}")
                    except json.JSONDecodeError:
                        args = {}
                self.on_event(f"  [tool] {fn['name']}({args})")
                result = self._execute(fn["name"], args)
                self.on_event(f"  [result] {result}")
                messages.append({"role": "tool", "tool_call_id": c.get("id", f"call_{i}"),
                                 "name": fn["name"], "content": json.dumps(result)})
        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": final}]
        return final
