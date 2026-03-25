#!/usr/bin/env python3
"""
UserPromptSubmit Hook — 情境觸發記憶提取 + System 1 快速判斷

每次使用者送出 prompt 時執行（在 Claude 處理之前）。

模擬人類認知:
1. 杏仁核: 快速情緒掃描（緊急？正面？負面？）
2. 海馬迴: 用 prompt 中的關鍵字觸發擴散激活，喚醒相關記憶
3. 前額葉: 把相關記憶作為 additionalContext 注入

和 SessionStart 的差異:
- SessionStart: 載入「一直都重要的」記憶（姓名、核心偏好）
- UserPromptSubmit: 載入「和當前問題相關的」記憶（情境觸發）

輸入 (stdin): {"session_id":"...", "message":{"role":"user","content":"..."}, ...}
輸出 (stdout): {"additionalContext": "被喚醒的記憶..."} 
"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import MemoryNetwork

def emotional_scan(text: str) -> dict:
    """
    System 1 快速情緒掃描 — 模擬杏仁核

    在理性分析之前先感知情緒信號
    """
    text_lower = text.lower()
    urgency = 0.0
    valence = 0.0

    urgent = ["緊急", "馬上", "立刻", "urgent", "asap", "壞了", "崩潰", "error", "bug", "crash"]
    positive = ["謝謝", "太好了", "棒", "喜歡", "愛", "感謝", "great", "love", "awesome", "完成"]
    negative = ["煩", "糟", "討厭", "錯誤", "失敗", "不行", "hate", "fail", "broken", "問題"]

    for w in urgent:
        if w in text_lower:
            urgency = min(1.0, urgency + 0.3)
    for w in positive:
        if w in text_lower:
            valence = min(1.0, valence + 0.2)
    for w in negative:
        if w in text_lower:
            valence = max(-1.0, valence - 0.2)

    return {"urgency": urgency, "valence": valence, "intensity": abs(valence) + urgency}


def main():
    try:
        event_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    # 提取使用者的 prompt 文字
    message = event_data.get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        # 可能是 multi-part content
        content = " ".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not content:
        sys.exit(0)

    network = MemoryNetwork()
    if network.count == 0:
        sys.exit(0)

    # ---- 1. 情緒掃描 ----
    emotions = emotional_scan(content)

    # ---- 2. 擴散激活: 用 prompt 觸發記憶 ----
    seeds = network.find_seeds(content)

    if not seeds:
        # 沒有直接匹配，不注入（SessionStart 已經載入了核心記憶）
        sys.exit(0)

    activated = network.spreading_activation(
        seed_ids=seeds,
        max_depth=3,
        decay=0.5,
        threshold=0.15,
    )

    if not activated:
        sys.exit(0)

    # 過濾掉 SessionStart 已經載入的高重要度記憶（避免重複）
    contextual = [(n, a) for n, a in activated if n.importance < 0.7]

    if not contextual:
        sys.exit(0)

    # ---- 3. 組裝 additionalContext ----
    top = contextual[:5]
    lines = ["[情境記憶] 以下記憶被當前對話喚醒："]
    for node, activation in top:
        strength = "強" if activation > 0.5 else "中" if activation > 0.2 else "弱"
        lines.append(f"- [{node.category}] {node.content} (關聯:{strength})")

    # 情緒提示
    if emotions["urgency"] > 0.5:
        lines.append("[提示] 使用者語氣較為緊急，優先處理核心問題。")
    if emotions["valence"] < -0.3:
        lines.append("[提示] 使用者可能遇到困難，語氣較為消極。")

    output = {"additionalContext": "\n".join(lines)}
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)

if __name__ == "__main__":
    main()
