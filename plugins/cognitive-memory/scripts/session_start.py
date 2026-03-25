#!/usr/bin/env python3
"""
SessionStart Hook — 模擬「起床」

Claude Code 每次啟動 session 時執行。

1. 檢查是否需要睡眠鞏固（距上次 > 24h）
2. 需要的話執行四階段鞏固
3. 載入高重要度記憶，透過 additionalContext 注入對話

輸入 (stdin): {"session_id": "...", "cwd": "...", ...}
輸出 (stdout): {"additionalContext": "記憶內容..."} 
"""

import sys
import json
import os

# 載入同目錄下的 mcp_server.py 中的 MemoryNetwork
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import MemoryNetwork, _get_cwd_from_event, hook_log

def main():
    # 讀取 stdin（Claude Code 傳入的 session 資訊）
    try:
        event_data = json.loads(sys.stdin.read())
    except Exception:
        event_data = {}

    cwd = _get_cwd_from_event(event_data)
    network = MemoryNetwork(project_dir=cwd)
    hook_log("SessionStart", f"cwd={cwd}, storage={network._dir}, count={network.count}", network._dir)

    # ---- 1. 睡眠鞏固檢查 ----
    from datetime import datetime, timedelta
    last_sleep = network.get_last_sleep()
    needs_sleep = False

    if last_sleep:
        elapsed = datetime.now() - datetime.fromisoformat(last_sleep)
        hours = elapsed.total_seconds() / 3600
        if hours >= 24:
            needs_sleep = True
            print(f"🌙 距上次鞏固 {hours:.0f}h，開始記憶整理...", file=sys.stderr)
    elif network.count > 0:
        needs_sleep = True
        print("🌙 首次鞏固...", file=sys.stderr)

    if needs_sleep and network.count > 0:
        report = network.run_sleep_consolidation()
        for stage, summary in report.get("stages", {}).items():
            print(f"  {stage}: {summary}", file=sys.stderr)
        print(f"  節點: {report['nodes_before']}→{report['nodes_after']}", file=sys.stderr)

    # ---- 2. 載入重要記憶注入 additionalContext ----
    if network.count == 0:
        sys.exit(0)

    # 取高重要度記憶
    high = sorted(
        [n for n in network._nodes.values() if n.importance >= 0.7],
        key=lambda n: n.importance, reverse=True
    )[:8]

    # 取最近存取的記憶
    from datetime import timedelta as td
    cutoff = (datetime.now() - td(hours=48)).isoformat()
    recent = sorted(
        [n for n in network._nodes.values()
         if n.last_accessed >= cutoff and n.importance < 0.7],
        key=lambda n: n.last_accessed, reverse=True
    )[:5]

    if not high and not recent:
        sys.exit(0)

    # 組裝
    lines = ["[認知記憶系統] 以下是你已知的關於使用者的資訊，請自然地運用："]
    if high:
        for n in high:
            lines.append(f"- [{n.category}] {n.content} (重要度:{n.importance:.2f})")
    if recent:
        high_ids = {n.id for n in high}
        for n in recent:
            if n.id not in high_ids:
                lines.append(f"- [近期] {n.content}")
    lines.append(f"(記憶庫共 {network.count} 條，可用 recall_memory 工具查詢更多)")
    lines.append("請不要提及「記憶系統」，像自然記得一樣使用這些資訊。")

    # 輸出 additionalContext → Claude Code 會注入到對話中
    output = {"additionalContext": "\n".join(lines)}
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
