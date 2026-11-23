"""Tool registry: every ability declares itself with @tool. The brain never changes when you add one."""
import importlib, inspect, pkgutil, typing
from dataclasses import dataclass
from typing import Callable

_JSON = {int: "integer", float: "number", str: "string", bool: "boolean"}


@dataclass
class Tool:
    name: str
    description: str
    risk: str            # "low" | "medium" | "high"
    fn: Callable
    schema: dict

    def spec(self) -> dict:
        """OpenAI-style function spec sent to the LLM."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description, "parameters": self.schema}}


TOOLS: dict[str, Tool] = {}


def _schema(fn) -> dict:
    sig, hints = inspect.signature(fn), typing.get_type_hints(fn)
    props, required = {}, []
    for name, p in sig.parameters.items():
        t = hints.get(name, str)
        if typing.get_origin(t) is typing.Literal:
            props[name] = {"type": "string", "enum": list(typing.get_args(t))}
        else:
            props[name] = {"type": _JSON.get(t, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def tool(description: str, risk: str = "low"):
    assert risk in ("low", "medium", "high")
    def deco(fn):
        TOOLS[fn.__name__] = Tool(fn.__name__, description, risk, fn, _schema(fn))
        return fn
    return deco


def load_plugins(packages=("actions", "skills")):
    """Import every module in the given packages so their @tool decorators run."""
    for pkg_name in packages:
        pkg = importlib.import_module(pkg_name)
        for m in pkgutil.iter_modules(pkg.__path__):
            importlib.import_module(f"{pkg_name}.{m.name}")


def call(name: str, args: dict) -> dict:
    t = TOOLS.get(name)
    if not t:
        return {"error": f"unknown tool '{name}'"}
    try:
        out = t.fn(**args)
        return out if isinstance(out, dict) else {"result": out}
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
