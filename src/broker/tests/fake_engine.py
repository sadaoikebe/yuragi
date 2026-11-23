"""A stand-in for yuragi.engine in the broker tests (Windows).

    python fake_engine.py STATE_DIR

STATE_DIR/plan.json lists what each start does, in order (the last entry repeats):
  "normal"                 ready, then one reply per request
  "oversized_ready"        ready with a diagnostic longer than the protocol's line limit
  "pending_conversion"     Space is settled by a timer, as with an async LM
Each start appends "pid birth" to STATE_DIR/starts.
"""
import json
import os
from pathlib import Path
import sys


def birth(pid: int):
    """When the running process with this pid started; None once it has exited.
    With the pid it names one process: Windows soon gives a freed pid to another."""
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    handle = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)
    if not handle:
        return None
    try:
        if kernel32.WaitForSingleObject(handle, 0) != 0x102:  # not WAIT_TIMEOUT: exited
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        kernel32.GetProcessTimes(handle, *map(ctypes.byref, times))
        return times[0].dwHighDateTime << 32 | times[0].dwLowDateTime
    finally:
        kernel32.CloseHandle(handle)


def main() -> int:
    state = Path(sys.argv[1])
    plan = json.loads((state / "plan.json").read_text(encoding="utf-8"))
    starts = state / "starts"
    index = len(starts.read_text().splitlines()) if starts.exists() else 0
    with starts.open("a") as stream:
        stream.write(f"{os.getpid()} {birth(os.getpid())}\n")
    mode = plan[min(index, len(plan) - 1)]
    print(f"fake engine start {index} mode {json.dumps(mode)}", file=sys.stderr, flush=True)
    out = sys.stdout
    ready = {"ready": True, "proto": 1, "warnings": []}
    if mode == "oversized_ready":
        ready["diagnostic"] = "x" * (1024 * 1024)
    out.write(json.dumps(ready) + "\n")
    out.flush()
    pending = False
    for line in sys.stdin:
        msg = json.loads(line)
        if msg.get("op") in ("open", "close"):
            continue
        op = msg["op"]
        converted = pending and op == "timeout"
        pending = mode == "pending_conversion" and op == "up" and msg.get("vk") == 0x20
        out.write(json.dumps({"sid": msg["sid"], "seq": msg["seq"], "direct": False,
                              "composition": f"{op}:{msg.get('vk')}", "commit": "",
                              "converted": converted, "pending": pending,
                              "timer": msg["t"] + 10 if pending else None}) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
