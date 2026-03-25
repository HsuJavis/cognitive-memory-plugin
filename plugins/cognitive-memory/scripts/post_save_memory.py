#!/usr/bin/env python3
"""
PostToolUse Hook (matcher: mcp__cognitive-memory__save_memory)
Hebbian Learning — 記憶儲存後自動加強關聯

每次 Claude 用 save_memory 存了新記憶後：
1. 找到本次 session 中之前存的記憶
2. 新記憶和舊記憶之間建立連結（同次對話 = 共同激活）
3. 記錄 session 記憶 ID（供 Stop hook 使用）

模擬 Hebb 法則: "Neurons that fire together, wire together"

輸入 (stdin): {"tool_name":"mcp__cognitive-memory__save_memory","tool_input":{...},"tool_output":"..."}
"""

import sys
import json
import os
import fcntl
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import MemoryNetwork, _get_cwd_from_event, hook_log

def main():
    try:
        event = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    # 解析 tool_output 取得新記憶的 ID
    try:
        tool_output = event.get("tool_output", "")
        if isinstance(tool_output, str):
            result = json.loads(tool_output)
        else:
            result = tool_output
        new_id = result.get("id", "")
    except Exception:
        sys.exit(0)

    if not new_id:
        sys.exit(0)

    cwd = _get_cwd_from_event(event)
    network = MemoryNetwork(project_dir=cwd)
    hook_log("PostToolUse", f"save_memory new_id={new_id}, storage={network._dir}", network._dir)

    # 讀寫 session 檔案使用 file lock，避免並發時丟失資料
    session_id = event.get("session_id", "default")
    session_file = network._dir / f"session_{session_id}.json"

    # 使用 lock 檔案保護讀-改-寫操作
    lock_file = network._dir / f"session_{session_id}.lock"

    try:
        with open(lock_file, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)  # 排他鎖

            # 讀取當前 session 記憶列表
            session_ids = []
            if session_file.exists():
                try:
                    session_ids = json.loads(session_file.read_text())
                except Exception:
                    session_ids = []

            # Hebbian: 新記憶和本次 session 的所有已有記憶建立連結
            for existing_id in session_ids:
                if existing_id != new_id and existing_id in network._nodes:
                    network.connect(new_id, existing_id, weight=0.3)
                    print(
                        f"🧠 Hebb: 連結 {new_id[:8]} ↔ {existing_id[:8]}",
                        file=sys.stderr,
                    )

            # 記錄新 ID
            session_ids.append(new_id)
            session_file.write_text(json.dumps(session_ids), encoding="utf-8")

            fcntl.flock(lf, fcntl.LOCK_UN)  # 釋放鎖
    except Exception as e:
        print(f"⚠️ Hebbian hook 錯誤: {e}", file=sys.stderr)

    # 清理 lock 檔案（非必要，但保持乾淨）
    lock_file.unlink(missing_ok=True)

    sys.exit(0)

if __name__ == "__main__":
    main()
