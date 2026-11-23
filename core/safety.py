"""Safety gate: decides allow / confirm / deny before any tool runs."""
import json, os, re, time
import config

DENY_PATTERNS = [
    r"\brm\s+(-\w+\s+)*-\w*r\w*\s+(-\w+\s+)*(/|~|\$HOME)(\s|$|\*)",   # rm -rf / or ~
    r"\bmkfs\b", r"\bdd\s+.*of=/dev/", r">\s*/dev/(sd|nvme|vd)",
    r":\(\)\s*\{", r"\bchmod\s+-R\s+777\s+/(\s|$)", r"\bshred\b.*/dev/",
]


def check(tool, args: dict) -> str:
    """Returns 'allow', 'confirm' or 'deny'."""
    if tool.name == "run_shell":
        cmd = args.get("command", "")
        if any(re.search(p, cmd) for p in DENY_PATTERNS):
            return "deny"
        return "confirm"
    if tool.risk == "high":
        return "confirm"
    return "allow"


def log_action(name: str, args: dict, decision: str, result: dict):
    os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
    with open(config.LOG_PATH, "a") as f:
        f.write(json.dumps({"t": time.strftime("%F %T"), "tool": name, "args": args,
                            "decision": decision, "result": str(result)[:300]}) + "\n")
