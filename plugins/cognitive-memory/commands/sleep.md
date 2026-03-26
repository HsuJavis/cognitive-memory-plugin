---
description: 手動觸發記憶鞏固 — 模擬睡眠，整理記憶網路
---

請使用 cognitive-memory MCP server 的 `trigger_sleep` 工具執行記憶鞏固。

鞏固完成後，清楚說明每個階段做了什麼：
1. 記憶重播 — 加強了哪些連結
2. 突觸修剪 — 清理了多少弱連結
3. 模式提取 — 從情節記憶中歸納出了什麼模式
4. 記憶整合 — 建立了哪些新的語意關聯
5. 深度遺忘 — 遺忘了多少條記憶

**重要：如果回傳結果包含 `pending_refinement`，你必須用 Agent subagent 精煉摘要：**

對每個 pending cluster，啟動一個 Agent（使用 model: haiku 以節省資源），prompt 範例：

```
你是記憶歸納專家。將以下多條記憶歸納為一句精確的繁體中文摘要。
只輸出摘要本身，不要前綴、解釋或格式標記。

主題：{topic}
記憶內容：
{contents 逐條列出}
```

Agent 回傳摘要後，用 `update_memory` 工具更新對應 `semantic_id` 的 `content` 欄位。
多個 cluster 可以平行啟動多個 Agent。

最後對比鞏固前後的記憶網路變化。
