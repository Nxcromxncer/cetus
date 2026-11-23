"""Shell access. Always requires spoken/typed confirmation (see core/safety.py)."""
import subprocess
from core.registry import tool


@tool("Run a shell command in bash and return its output. Use for tasks no other tool covers (files, git, pacman queries, etc).", risk="high")
def run_shell(command: str, timeout: int = 30):
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout}s"}
    return {"exit_code": p.returncode, "stdout": p.stdout[-2000:], "stderr": p.stderr[-1000:]}
