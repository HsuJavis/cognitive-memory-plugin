#!/usr/bin/env python3
"""
Stop Hook — Session 結束時的記憶處理

Claude 完成回覆時執行。

1. 規則式自動提取記憶（從累積的對話中提取，不呼叫 LLM）
2. 讀取本次 session 的記憶 ID 列表
3. 最終加強 session 內記憶的互相連結
4. 記錄 session 摘要（供睡眠鞏固使用）
5. 清理臨時檔案

模擬：白天結束時海馬迴標記「今天的重要事件」+ 自動編碼新記憶

輸入 (stdin): {"session_id":"...", "stop_hook_active": false, ...}
"""

import sys
import json
import os
import re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import MemoryNetwork, MemoryNode, _get_cwd_from_event


# ============================================================================
#  規則式記憶提取 — 不呼叫 LLM，純 pattern matching
# ============================================================================

def extract_memories_from_transcript(messages: list[str]) -> list[dict]:
    """
    從使用者訊息中用規則提取值得記住的資訊。

    每條規則返回: {"content", "category", "importance", "tags", "emotional_valence"}
    """
    extracted = []
    seen_contents = set()  # 去重

    for text in messages:
        text = text.strip()
        if not text or len(text) < 3:
            continue

        # ---- Rule 1: 明確記住請求 ----
        # "記住：XXX" / "remember: XXX"
        for keyword in ["記住", "幫我記", "請記住"]:
            if keyword in text:
                idx = text.index(keyword) + len(keyword)
                rest = text[idx:].lstrip(":： \t")
                if rest and rest not in seen_contents:
                    seen_contents.add(rest)
                    extracted.append({
                        "content": rest,
                        "category": "fact",
                        "importance": 0.85,
                        "tags": ["user-request"],
                        "emotional_valence": 0.0,
                        "emotional_intensity": 0.3,
                    })
                break
        m = re.search(r"(?:remember|memo)[:\s]+(.+)", text, re.I)
        if m:
            rest = m.group(1).strip()
            if rest and rest not in seen_contents:
                seen_contents.add(rest)
                extracted.append({
                    "content": rest,
                    "category": "fact",
                    "importance": 0.85,
                    "tags": ["user-request"],
                    "emotional_valence": 0.0,
                    "emotional_intensity": 0.3,
                })

        # ---- Rule 2: 身份資訊 ----
        # "我叫XXX" / "我的名字是XXX" / "my name is XXX"
        for pattern, label in [
            (r"我叫\s*([^\s,，。.!！?？]{1,10})", "name"),
            (r"我的名字是\s*([^\s,，。.!！?？]{1,10})", "name"),
            (r"(?:my name is|i'?m)\s+(\S{1,20})", "name"),
        ]:
            m = re.search(pattern, text, re.I)
            if m:
                name = m.group(1).strip()
                content = f"使用者的名字: {name}"
                if content not in seen_contents:
                    seen_contents.add(content)
                    extracted.append({
                        "content": content,
                        "category": "fact",
                        "importance": 0.9,
                        "tags": ["identity", "name"],
                        "emotional_valence": 0.1,
                        "emotional_intensity": 0.2,
                    })
                break

        # ---- Rule 3: 角色/工作 ----
        # "我是XXX" / "我的工作是XXX" / "我負責XXX"
        for pattern in [
            r"我是(?:一[個名位])?([^\s,，。]{2,20})",
            r"我(?:的工作|職業)是\s*([^\s,，。]{2,20})",
            r"我負責\s*([^\s,，。]{2,30})",
        ]:
            m = re.search(pattern, text)
            if m:
                role = m.group(1).strip()
                # 過濾太短或常見語氣詞
                if len(role) >= 2 and role not in {"想要", "覺得", "認為", "希望", "說"}:
                    content = f"使用者的角色: {role}"
                    if content not in seen_contents:
                        seen_contents.add(content)
                        extracted.append({
                            "content": content,
                            "category": "fact",
                            "importance": 0.8,
                            "tags": ["identity", "role"],
                            "emotional_valence": 0.0,
                            "emotional_intensity": 0.1,
                        })
                break

        # ---- Rule 4: 偏好 ----
        # "我喜歡XXX" / "我偏好XXX" / "我習慣XXX"
        for pattern in [
            r"我(?:喜歡|偏好|愛用|習慣用?)\s*([^\s,，。]{2,30})",
            r"I (?:prefer|like|love)\s+(.{2,30}?)(?:\.|,|$)",
        ]:
            m = re.search(pattern, text, re.I)
            if m:
                pref = m.group(1).strip()
                content = f"使用者偏好: {pref}"
                if content not in seen_contents:
                    seen_contents.add(content)
                    extracted.append({
                        "content": content,
                        "category": "preference",
                        "importance": 0.7,
                        "tags": ["preference"],
                        "emotional_valence": 0.3,
                        "emotional_intensity": 0.2,
                    })
                break

        # ---- Rule 5: 負面偏好 / 修正 ----
        # "不要XXX" / "別XXX" / "不想XXX"
        for pattern in [
            r"(?:不要|別|不想|不喜歡)\s*([^,，。.!！?？\n]{2,50})",
            r"(?:don'?t|never|stop)\s+([^.!?\n]{2,50}?)(?:\.|,|!|$)",
        ]:
            m = re.search(pattern, text, re.I)
            if m:
                neg = m.group(1).strip()
                content = f"使用者不喜歡: {neg}"
                if content not in seen_contents:
                    seen_contents.add(content)
                    extracted.append({
                        "content": content,
                        "category": "preference",
                        "importance": 0.7,
                        "tags": ["preference", "negative"],
                        "emotional_valence": -0.3,
                        "emotional_intensity": 0.3,
                    })
                break

        # ---- Rule 6: 專案/技術上下文 ----
        # "我們的專案XXX" / "這個專案XXX" / "我正在做XXX"
        for pattern in [
            r"(?:我們的|這個)專案\s*([^\s,，。]{2,30})",
            r"我正在(?:做|開發|研究)\s*([^\s,，。]{2,30})",
            r"(?:the|our|this) project\s+(.{2,30}?)(?:\.|,|$)",
        ]:
            m = re.search(pattern, text, re.I)
            if m:
                proj = m.group(1).strip()
                content = f"專案上下文: {proj}"
                if content not in seen_contents:
                    seen_contents.add(content)
                    extracted.append({
                        "content": content,
                        "category": "context",
                        "importance": 0.6,
                        "tags": ["project"],
                        "emotional_valence": 0.0,
                        "emotional_intensity": 0.1,
                    })
                break

    return extracted


# ============================================================================
#  主流程
# ============================================================================

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
    cwd = _get_cwd_from_event(event)
    network = MemoryNetwork(project_dir=cwd)

    # ---- 1. 規則式自動提取記憶 ----
    transcript_file = network._dir / f"session_{session_id}_transcript.jsonl"
    auto_extracted_ids = []

    if transcript_file.exists():
        try:
            messages = []
            for line in transcript_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    entry = json.loads(line)
                    messages.append(entry.get("content", ""))

            memories = extract_memories_from_transcript(messages)

            for mem in memories:
                # 檢查是否已有相似記憶（避免重複）
                seeds = network.find_seeds(mem["content"])
                if seeds:
                    # 已有相關記憶，跳過
                    continue

                node = MemoryNode(
                    id="",
                    content=mem["content"],
                    category=mem["category"],
                    importance=mem["importance"],
                    emotional_valence=mem.get("emotional_valence", 0.0),
                    emotional_intensity=mem.get("emotional_intensity", 0.1),
                    tags=mem["tags"],
                    source="auto-extract",  # 標記為自動提取
                )
                saved = network.add(node)
                auto_extracted_ids.append(saved.id)

                # 自動關聯
                content_seeds = network.find_seeds(mem["content"])
                for sid in content_seeds:
                    if sid != saved.id:
                        network.connect(saved.id, sid, weight=0.3)

            if auto_extracted_ids:
                print(
                    f"🧠 自動提取: {len(auto_extracted_ids)} 條記憶 "
                    f"({', '.join(m['category'] for m in memories[:3])})",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"⚠️ 自動提取失敗: {e}", file=sys.stderr)

        # 清理 transcript 檔案
        transcript_file.unlink(missing_ok=True)

    # ---- 2. 讀取 session 記憶列表 ----
    session_file = network._dir / f"session_{session_id}.json"
    session_ids = []
    if session_file.exists():
        try:
            session_ids = json.loads(session_file.read_text())
        except Exception:
            pass

    # 合併自動提取的 ID
    session_ids.extend(auto_extracted_ids)

    if session_ids:
        # ---- 3. 最終 Hebbian 加強 ----
        # Session 結束 = 共同經歷完成，再加強一次連結
        for i, id_a in enumerate(session_ids):
            for id_b in session_ids[i + 1:]:
                if id_a in network._nodes and id_b in network._nodes:
                    network.connect(id_a, id_b, weight=0.15)

        # ---- 4. 記錄 session 日誌（供鞏固用）----
        log_dir = network._dir / "session_logs"
        log_dir.mkdir(exist_ok=True)
        log = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "memory_ids": session_ids,
            "memory_count": len(session_ids),
            "auto_extracted": len(auto_extracted_ids),
        }
        log_file = log_dir / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_file.write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")

        print(
            f"🧠 Session 結束: {len(session_ids)} 條記憶已加強連結"
            + (f" (含 {len(auto_extracted_ids)} 條自動提取)" if auto_extracted_ids else ""),
            file=sys.stderr,
        )

        # 清理臨時 session 檔案
        session_file.unlink(missing_ok=True)

    network._save()
    sys.exit(0)

if __name__ == "__main__":
    main()
