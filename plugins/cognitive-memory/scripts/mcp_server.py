#!/usr/bin/env python3
"""
認知記憶 MCP Server — Cognitive Memory MCP Server
用於 Claude Code 的持久記憶系統

MCP 傳輸: stdio（標準輸入/輸出）
工具: save_memory, recall_memory, forget_memory, list_memories, trigger_sleep, sleep_status

此檔案是自包含的（self-contained），不依賴 react_agent.py 或 cognitive_agent.py。
所有記憶網路邏輯和睡眠鞏固邏輯都包含在內。

安裝依賴:
  pip install mcp anthropic

啟動（通常由 Claude Code 透過 .mcp.json 自動啟動）:
  python3 mcp_server.py
"""

import os
import sys
import json
import math
import hashlib
import logging
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================================
#  日誌 — 寫到 stderr（MCP server 的 stdout 用於 JSON-RPC 通訊）
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("cognitive-memory-mcp")


# ============================================================================
#  記憶節點 — MemoryNode
# ============================================================================

@dataclass
class MemoryNode:
    """記憶網路中的一個節點"""
    id: str
    content: str
    category: str = "episodic"        # episodic / semantic / procedural
    importance: float = 0.5
    emotional_valence: float = 0.0    # -1.0(負面) ~ +1.0(正面)
    emotional_intensity: float = 0.0  # 0.0(平淡) ~ 1.0(強烈)
    activation: float = 0.0
    connections: dict = field(default_factory=dict)  # {other_id: weight}
    tags: list = field(default_factory=list)
    source: str = "tool"
    abstraction_level: int = 0        # 0=具體事件, 1=歸納, 2=抽象原則
    created_at: str = ""
    last_accessed: str = ""
    access_count: int = 0

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.last_accessed:
            self.last_accessed = now
        if not self.id:
            self.id = hashlib.md5(
                f"{self.content}{self.created_at}".encode()
            ).hexdigest()[:12]


# ============================================================================
#  關聯式記憶網路 — Associative Memory Network
# ============================================================================

class MemoryNetwork:
    """
    關聯式記憶網路 — 支援擴散激活的持久記憶儲存

    儲存位置: ~/.cognitive-memory/memory_network.json
    （可透過 COGNITIVE_MEMORY_DIR 環境變數修改）
    """

    def __init__(self, storage_dir: Optional[str] = None):
        self._dir = Path(
            storage_dir
            or os.environ.get("COGNITIVE_MEMORY_DIR")
            or os.path.expanduser("~/.cognitive-memory")
        )
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "memory_network.json"
        self._meta_file = self._dir / "last_sleep.json"
        self._sleep_log_dir = self._dir / "sleep_logs"
        self._sleep_log_dir.mkdir(exist_ok=True)
        self._nodes: dict[str, MemoryNode] = {}
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text(encoding="utf-8"))
                for nid, ndata in data.items():
                    self._nodes[nid] = MemoryNode(**ndata)
                logger.info(f"載入 {len(self._nodes)} 個記憶節點")
            except Exception as e:
                logger.warning(f"載入失敗: {e}")

    def _save(self):
        data = {nid: asdict(n) for nid, n in self._nodes.items()}
        self._file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, node: MemoryNode) -> MemoryNode:
        """新增或更新記憶節點"""
        if node.id in self._nodes:
            existing = self._nodes[node.id]
            existing.access_count += 1
            existing.last_accessed = datetime.now().isoformat()
            existing.importance = max(existing.importance, node.importance)
            self._save()
            return existing
        self._nodes[node.id] = node
        self._save()
        return node

    def delete(self, nid: str) -> bool:
        if nid in self._nodes:
            # 清理連結
            for other in self._nodes.values():
                other.connections.pop(nid, None)
            del self._nodes[nid]
            self._save()
            return True
        return False

    def connect(self, id_a: str, id_b: str, weight: float = 0.5):
        """建立/加強雙向連結（Hebb 法則）"""
        if id_a in self._nodes and id_b in self._nodes:
            a, b = self._nodes[id_a], self._nodes[id_b]
            a.connections[id_b] = min(1.0, a.connections.get(id_b, 0) + weight)
            b.connections[id_a] = min(1.0, b.connections.get(id_a, 0) + weight)
            self._save()

    def find_seeds(self, text: str) -> list[str]:
        """從文字中找到匹配的種子節點（擴散激活的起點）"""
        text_lower = text.lower()
        words = [w for w in text_lower.split() if len(w) > 1]
        seeds = []
        for node in self._nodes.values():
            searchable = f"{node.content} {' '.join(node.tags)}".lower()
            if any(w in searchable for w in words):
                seeds.append(node.id)
            elif any(tag.lower() in text_lower for tag in node.tags if len(tag) > 1):
                seeds.append(node.id)
        return seeds

    def spreading_activation(
        self, seed_ids: list[str], max_depth: int = 3,
        decay: float = 0.5, threshold: float = 0.1,
    ) -> list[tuple[MemoryNode, float]]:
        """
        擴散激活 — 從種子節點沿著連結擴散

        模擬人腦的擴散激活: 想到 A → 連帶想到 B → 連帶想到 C
        每經過一層連結，激活能量衰減
        """
        for n in self._nodes.values():
            n.activation = 0.0

        activated: dict[str, float] = {}
        queue = []
        for sid in seed_ids:
            if sid in self._nodes:
                activated[sid] = 1.0
                self._nodes[sid].activation = 1.0
                queue.append((sid, 1.0, 0))

        while queue:
            cid, cact, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            node = self._nodes[cid]
            for nid, weight in node.connections.items():
                if nid not in self._nodes:
                    continue
                spread = cact * weight * decay
                if spread < threshold:
                    continue
                if spread > activated.get(nid, 0):
                    activated[nid] = spread
                    self._nodes[nid].activation = spread
                    queue.append((nid, spread, depth + 1))

        results = [(self._nodes[nid], act) for nid, act in activated.items()]
        results.sort(key=lambda x: x[1], reverse=True)
        for node, _ in results:
            node.last_accessed = datetime.now().isoformat()
            node.access_count += 1
        self._save()
        return results

    # ---- 睡眠鞏固 (Sleep Consolidation) ----

    def get_last_sleep(self) -> Optional[str]:
        if self._meta_file.exists():
            try:
                return json.loads(self._meta_file.read_text()).get("last_sleep")
            except Exception:
                pass
        return None

    def record_sleep(self):
        self._meta_file.write_text(
            json.dumps({"last_sleep": datetime.now().isoformat()}), encoding="utf-8"
        )

    def run_sleep_consolidation(self, llm_summarize_fn=None) -> dict:
        """
        完整的睡眠鞏固循環

        Stage 1: 記憶重播 — 加強近期活躍記憶的連結
        Stage 2: 突觸修剪 — 全域衰減 + 刪除弱連結
        Stage 3: 模式提取 — 聚類 episodic → 產出 semantic
        Stage 4: 記憶整合 — 新舊 semantic 間建立連結
        清理:    深度遺忘 — 移除極低重要度的記憶
        """
        report = {"started_at": datetime.now().isoformat(), "stages": {}}
        nodes_before = len(self._nodes)
        conns_before = sum(len(n.connections) for n in self._nodes.values()) // 2

        # ---- Stage 1: 記憶重播 ----
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        recent = [n for n in self._nodes.values() if n.last_accessed >= cutoff]
        recent.sort(key=lambda n: n.access_count * (1 + n.emotional_intensity), reverse=True)
        strengthened = 0
        for i, a in enumerate(recent):
            for b in recent[i + 1:]:
                existing = a.connections.get(b.id, 0)
                boost = 0.15 * (1 + max(a.emotional_intensity, b.emotional_intensity) * 0.5)
                if existing > 0:
                    a.connections[b.id] = min(1.0, existing + boost)
                    b.connections[a.id] = min(1.0, b.connections.get(a.id, 0) + boost)
                    strengthened += 1
                elif set(a.tags) & set(b.tags):
                    weak = boost * 0.5
                    a.connections[b.id] = weak
                    b.connections[a.id] = weak
                    strengthened += 1
        report["stages"]["1_replay"] = f"重播 {len(recent)} 條, 加強 {strengthened} 條連結"

        # ---- Stage 2: 突觸修剪 ----
        pruned = 0
        for node in self._nodes.values():
            new_conns = {}
            for nid, w in node.connections.items():
                w2 = w * 0.9
                if w2 >= 0.05:
                    new_conns[nid] = w2
                else:
                    pruned += 1
            node.connections = new_conns
            if node.importance < 0.85:
                node.importance *= 0.95
        report["stages"]["2_prune"] = f"修剪 {pruned // 2} 條弱連結"

        # ---- Stage 3: 模式提取 ----
        episodic = [n for n in self._nodes.values()
                    if n.category == "episodic" and n.abstraction_level == 0
                    and "consolidated" not in n.tags]
        # 簡單聚類: connected components
        visited = set()
        clusters = []
        for node in episodic:
            if node.id in visited:
                continue
            cluster = []
            queue = [node]
            ep_ids = {n.id for n in episodic}
            while queue:
                cur = queue.pop(0)
                if cur.id in visited:
                    continue
                visited.add(cur.id)
                cluster.append(cur)
                for nid in cur.connections:
                    if nid in ep_ids and nid not in visited and nid in self._nodes:
                        queue.append(self._nodes[nid])
            if len(cluster) >= 3:
                clusters.append(cluster)

        extracted = 0
        for cluster in clusters[:5]:
            all_tags = [t for n in cluster for t in n.tags]
            common = [t for t in set(all_tags) if all_tags.count(t) >= 2] or ["general"]

            if llm_summarize_fn:
                contents = [f"- {n.content}" for n in cluster]
                summary = llm_summarize_fn(contents, common[0])
            else:
                snippets = [n.content[:30] for n in cluster[:4]]
                summary = f"關於「{common[0]}」的歸納: {'; '.join(snippets)}"

            sem = MemoryNode(
                id="", content=summary, category="semantic",
                importance=max(n.importance for n in cluster) * 0.85,
                emotional_valence=sum(n.emotional_valence for n in cluster) / len(cluster),
                emotional_intensity=max(n.emotional_intensity for n in cluster) * 0.7,
                tags=common, source="sleep", abstraction_level=1,
            )
            saved = self.add(sem)
            for node in cluster:
                self.connect(saved.id, node.id, weight=0.7)
                node.importance *= 0.6
                if "consolidated" not in node.tags:
                    node.tags.append("consolidated")
            extracted += 1
        report["stages"]["3_extract"] = f"提取 {extracted} 個模式"

        # ---- Stage 4: 整合 ----
        semantics = [n for n in self._nodes.values() if n.category == "semantic"]
        new_conns = 0
        for i, a in enumerate(semantics):
            for b in semantics[i + 1:]:
                if b.id in a.connections:
                    continue
                overlap = len(set(a.tags) & set(b.tags))
                if overlap > 0:
                    self.connect(a.id, b.id, weight=min(0.4, overlap * 0.15))
                    new_conns += 1
        report["stages"]["4_integrate"] = f"建立 {new_conns} 條 semantic 間連結"

        # ---- 清理: 深度遺忘 ----
        to_remove = []
        for node in list(self._nodes.values()):
            if node.abstraction_level >= 1:
                continue
            if node.emotional_intensity > 0.6:
                continue
            if node.importance < 0.05:
                to_remove.append(node.id)
        for nid in to_remove:
            self.delete(nid)
        report["stages"]["5_forget"] = f"深度遺忘 {len(to_remove)} 條"

        self._save()
        self.record_sleep()

        # 儲存報告
        report["finished_at"] = datetime.now().isoformat()
        report["nodes_before"] = nodes_before
        report["nodes_after"] = len(self._nodes)
        report["connections_before"] = conns_before
        report["connections_after"] = sum(len(n.connections) for n in self._nodes.values()) // 2

        log_file = self._sleep_log_dir / f"sleep_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        log_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        return report

    @property
    def count(self) -> int:
        return len(self._nodes)


# ============================================================================
#  MCP Server — 使用 mcp 套件的 stdio 傳輸
# ============================================================================

def create_server():
    """建立 MCP Server 並註冊所有工具"""
    from mcp.server.fastmcp import FastMCP

    # 初始化記憶網路
    network = MemoryNetwork()

    # 建立 MCP Server
    mcp = FastMCP(
        "cognitive-memory",
        instructions="認知記憶系統 — 擴散激活、睡眠鞏固、情緒標記",
    )

    # ================================================================
    #  Tool 1: save_memory — 儲存記憶
    # ================================================================

    @mcp.tool()
    def save_memory(
        content: str,
        category: str = "episodic",
        importance: float = 0.5,
        tags: list[str] = [],
        emotional_valence: float = 0.0,
    ) -> str:
        """
        儲存一條記憶到認知記憶網路。

        記憶會自動和已有記憶建立關聯（擴散激活網路）。
        importance ≥ 0.7 的記憶會在 SKILL 載入時被標記為重要。

        Args:
            content: 要記住的內容
            category: 分類 (fact/preference/context/episodic)
            importance: 重要度 0.0~1.0
            tags: 標籤列表，用於關聯和檢索
            emotional_valence: 情緒效價 -1.0(負面)~+1.0(正面)
        """
        node = MemoryNode(
            id="",
            content=content,
            category=category,
            importance=importance,
            emotional_valence=emotional_valence,
            emotional_intensity=abs(emotional_valence),
            tags=tags,
            source="tool",
        )
        saved = network.add(node)

        # 自動關聯: 找到相關記憶並建立連結
        seeds = network.find_seeds(content)
        linked = 0
        for sid in seeds:
            if sid != saved.id:
                network.connect(saved.id, sid, weight=0.4)
                linked += 1

        return json.dumps({
            "status": "saved",
            "id": saved.id,
            "importance": saved.importance,
            "connections": linked,
            "total_memories": network.count,
            "note": "下次對話會自動記得" if importance >= 0.7 else "",
        }, ensure_ascii=False)

    # ================================================================
    #  Tool 2: recall_memory — 擴散激活搜尋
    # ================================================================

    @mcp.tool()
    def recall_memory(query: str, limit: int = 5) -> str:
        """
        用擴散激活搜尋記憶。

        不只是關鍵字匹配，會沿著記憶網路的關聯連結擴散，
        找到直接相關和間接相關的記憶。

        Args:
            query: 搜尋關鍵字
            limit: 返回筆數上限
        """
        seeds = network.find_seeds(query)
        if not seeds:
            # 退回到高重要度記憶
            important = sorted(
                network._nodes.values(),
                key=lambda n: n.importance, reverse=True
            )[:3]
            if important:
                seeds = [n.id for n in important]
            else:
                return json.dumps({
                    "results": [],
                    "message": f"找不到與 '{query}' 相關的記憶",
                }, ensure_ascii=False)

        activated = network.spreading_activation(seeds, max_depth=3)

        return json.dumps({
            "results": [
                {
                    "id": n.id,
                    "content": n.content,
                    "category": n.category,
                    "activation": round(a, 2),
                    "importance": round(n.importance, 2),
                    "tags": n.tags,
                    "connections": len(n.connections),
                    "access_count": n.access_count,
                }
                for n, a in activated[:limit]
            ],
            "total_activated": len(activated),
            "seeds_found": len(seeds),
        }, ensure_ascii=False)

    # ================================================================
    #  Tool 3: forget_memory — 刪除記憶
    # ================================================================

    @mcp.tool()
    def forget_memory(memory_id: str) -> str:
        """
        刪除一條記憶。

        Args:
            memory_id: 要刪除的記憶 ID（從 recall_memory 結果中取得）
        """
        deleted = network.delete(memory_id)
        return json.dumps({
            "status": "deleted" if deleted else "not_found",
            "memory_id": memory_id,
        }, ensure_ascii=False)

    # ================================================================
    #  Tool 4: list_memories — 記憶庫概覽
    # ================================================================

    @mcp.tool()
    def list_memories() -> str:
        """列出記憶庫的概覽: 各分類數量、最重要的記憶、網路統計。"""
        nodes = list(network._nodes.values())
        if not nodes:
            return json.dumps({"total": 0, "message": "記憶庫為空"}, ensure_ascii=False)

        # 按分類統計
        cats: dict[str, list] = {}
        for n in nodes:
            cats.setdefault(n.category, []).append(n)

        categories = {}
        for cat, entries in cats.items():
            top = sorted(entries, key=lambda e: e.importance, reverse=True)[:3]
            categories[cat] = {
                "count": len(entries),
                "top": [{"id": e.id, "content": e.content[:60], "importance": round(e.importance, 2)} for e in top],
            }

        total_connections = sum(len(n.connections) for n in nodes) // 2
        avg_importance = sum(n.importance for n in nodes) / len(nodes)

        return json.dumps({
            "total": len(nodes),
            "categories": categories,
            "network_stats": {
                "total_connections": total_connections,
                "avg_importance": round(avg_importance, 2),
                "semantic_count": sum(1 for n in nodes if n.category == "semantic"),
                "episodic_count": sum(1 for n in nodes if n.category == "episodic"),
            },
        }, ensure_ascii=False)

    # ================================================================
    #  Tool 5: trigger_sleep — 手動觸發睡眠鞏固
    # ================================================================

    @mcp.tool()
    def trigger_sleep() -> str:
        """
        手動觸發記憶鞏固（模擬睡眠）。

        執行四個階段:
        1. 記憶重播 — 加強近期活躍記憶的連結
        2. 突觸修剪 — 清理弱連結，降低不活躍記憶的重要度
        3. 模式提取 — 將相似的情節記憶歸納為語意記憶
        4. 記憶整合 — 新舊語意記憶之間建立關聯

        建議每天執行一次（SessionStart Hook 會自動檢查）。
        """
        report = network.run_sleep_consolidation()
        stages_summary = "\n".join(
            f"  {k}: {v}" for k, v in report["stages"].items()
        )
        return json.dumps({
            "status": "completed",
            "duration": report.get("finished_at", ""),
            "nodes": f"{report['nodes_before']} → {report['nodes_after']}",
            "connections": f"{report['connections_before']} → {report['connections_after']}",
            "stages": report["stages"],
        }, ensure_ascii=False)

    # ================================================================
    #  Tool 6: sleep_status — 查看鞏固狀態
    # ================================================================

    @mcp.tool()
    def sleep_status() -> str:
        """查看記憶鞏固狀態: 上次鞏固時間、是否需要鞏固、記憶網路統計。"""
        last = network.get_last_sleep()
        needs_sleep = True
        hours_since = None

        if last:
            elapsed = datetime.now() - datetime.fromisoformat(last)
            hours_since = round(elapsed.total_seconds() / 3600, 1)
            needs_sleep = hours_since >= 24

        nodes = list(network._nodes.values())
        return json.dumps({
            "last_sleep": last or "從未執行",
            "hours_since_last_sleep": hours_since,
            "needs_consolidation": needs_sleep,
            "memory_count": len(nodes),
            "semantic_count": sum(1 for n in nodes if n.category == "semantic"),
            "episodic_count": sum(1 for n in nodes if n.category == "episodic"),
            "total_connections": sum(len(n.connections) for n in nodes) // 2,
            "storage_path": str(network._dir),
        }, ensure_ascii=False)

    return mcp


# ============================================================================
#  入口
# ============================================================================

if __name__ == "__main__":
    server = create_server()
    server.run(transport="stdio")
