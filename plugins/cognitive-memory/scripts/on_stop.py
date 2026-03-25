#!/usr/bin/env python3
"""
Stop Hook — Session 結束時的記憶處理

Claude 完成回覆時執行。

1. 讀取本次 session 的記憶 ID 列表
2. 最終加強 session 內記憶的互相連結
3. 記錄 session 摘要（供睡眠鞏固使用）
4. 清理臨時 session 檔案

模擬：白天結束時海馬迴標記「今天的重要事件」

輸入 (stdin): {"session_id":"...", "stop_hook_active": false, ...}
"""

import sys
import json
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import MemoryNetwork

def main():
    try:
        event = json.loads(sys.stdin.read())
    except Exception:
        event = {}

    # 防止無限迴圈：Stop hook 返回 block 會讓 Claude 繼續，
    # 再次 Stop 時 stop_hook_active=true，此時直接放行
    if event.get("stop_hook_active"):
        sys.exit(0)

    session_id = event.get("session_id", "default")
    network = MemoryNetwork()

    # 讀取 session 記憶列表
    session_file = network._dir / f"session_{session_id}.json"
    session_ids = []
    if session_file.exists():
        try:
            session_ids = json.loads(session_file.read_text())
        except Exception:
            pass

    if session_ids:
        # ---- 最終 Hebbian 加強 ----
        # Session 結束 = 共同經歷完成，再加強一次連結
        for i, id_a in enumerate(session_ids):
            for id_b in session_ids[i + 1:]:
                if id_a in network._nodes and id_b in network._nodes:
                    network.connect(id_a, id_b, weight=0.15)

        # ---- 記錄 session 日誌（供鞏固用）----
        log_dir = network._dir / "session_logs"
        log_dir.mkdir(exist_ok=True)
        log = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "memory_ids": session_ids,
            "memory_count": len(session_ids),
        }
        log_file = log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_file.write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")

        print(
            f"🧠 Session 結束: {len(session_ids)} 條記憶已加強連結",
            file=sys.stderr,
        )

        # 清理臨時 session 檔案
        session_file.unlink(missing_ok=True)

    network._save()
    sys.exit(0)

if __name__ == "__main__":
    main()
