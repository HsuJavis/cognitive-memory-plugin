# Cognitive Memory Plugin for Claude Code

模擬人類認知記憶機制的 Claude Code 插件。

## 特性

- **擴散激活搜尋** — 記憶以網路形式儲存，搜尋時沿著關聯連結擴散
- **睡眠鞏固** — 週期性整理：重播加強、突觸修剪、模式提取、記憶整合
- **情境觸發** — 不是預載入所有記憶，而是被當前 prompt 的語意喚醒
- **Hebbian Learning** — 同次 session 中存的記憶自動建立連結
- **情緒標記** — 情緒越強烈的記憶越不容易被遺忘
- **安全守衛** — PreToolUse hook 攔截危險 Bash 命令
- **自動提取** — Stop/PreCompact 時從對話中規則式提取身份、偏好、事實
- **PreCompact 鞏固** — Context 壓縮前自動整合記憶，清除低價值 episodic，引導 compactor 產生更精簡的摘要
- **Agent 精煉** — Sleep 模式提取後，用 Agent subagent（獨立乾淨上下文）精煉語意摘要，不依賴 API key

## 安裝

```bash
# 依賴（透過 uv 自動管理，無需手動安裝）
# 需要: uv (https://github.com/astral-sh/uv)

# 在 Claude Code 中（GitHub 安裝）
/install-plugin https://github.com/HsuJavis/cognitive-memory-plugin

# 或本地安裝
/install-plugin /path/to/cognitive-memory-plugin
```

安裝後重啟 Claude Code，用 `/mcp` 確認 `cognitive-memory` server 已連線。

## 架構總覽

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code Session                      │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ SessionStart │───▶│  對話循環     │───▶│  Stop /      │   │
│  │ 起床         │    │              │    │  PreCompact  │   │
│  └──────┬───────┘    │  ┌────────┐  │    └──────┬───────┘   │
│         │            │  │ User   │  │           │           │
│  自動鞏固檢查     │  │ Prompt │  │    規則提取+鞏固     │
│  + 注入核心記憶   │  └───┬────┘  │    + 清理+compact引導│
│         │            │      │     │           │           │
│         │            │  ┌───▼────┐│           │           │
│         │            │  │情境觸發││           │           │
│         │            │  │+情緒掃描││           │           │
│         │            │  └───┬────┘│           │           │
│         │            │      │     │           │           │
│         │            │  ┌───▼────┐│           │           │
│         │            │  │安全守衛││           │           │
│         │            │  │(Bash)  ││           │           │
│         │            │  └───┬────┘│           │           │
│         │            │      │     │           │           │
│         │            │  ┌───▼────┐│           │           │
│         │            │  │Hebbian ││           │           │
│         │            │  │(save後)││           │           │
│         │            │  └────────┘│           │           │
│         │            └──────────────┘           │           │
│         │                                       │           │
│         ▼                                       ▼           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Memory Network (JSON)                   │   │
│  │  ~/.cognitive-memory/{project-slug}/                 │   │
│  │  memory_network.json                                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Hook 映射 — 認知機制 x Claude Code 原生事件

把人類認知的每個階段映射到 Claude Code 的原生 Hook 事件。

```
人類認知              Claude Code Hook        腳本                    做什麼
────────────────────────────────────────────────────────────────────────────────
起床（記憶已整理好）  SessionStart            session_start.py        睡眠鞏固檢查（>24h 自動執行）
                                                                      + 注入高重要度記憶 (additionalContext)

情境觸發記憶          UserPromptSubmit        on_user_prompt.py       用 prompt 語意做擴散激活
（看到冰淇淋想到小明）                                                + 注入情境記憶 (additionalContext)
                                                                      + System 1 情緒快速掃描
                                                                      + 情緒回饋更新被激活記憶

杏仁核警覺            PreToolUse (Bash)       safety_guard.py         偵測危險命令模式
（危險！快閃）                                                         → permissionDecision: "deny"

Hebb 法則             PostToolUse             post_save_memory.py     save_memory 後自動連結
（一起激活=一起連結）  (save_memory)                                   本次 session 的記憶互相加強

白天結束標記          Stop / SubagentStop     on_stop.py              從 transcript 規則式提取記憶
（海馬迴標記重要事件）                                                 + 最終 Hebbian 加強
                                                                      + 記錄 session 日誌

記憶壓縮前整理        PreCompact              on_stop.py              規則提取 + 自動 sleep 鞏固
                                                                      + 清除已鞏固的低價值 episodic
                                                                      + 注入 compact 引導 (additionalContext)
                                                                      → 告知 compactor 哪些已持久化可省略

睡覺整理              trigger_sleep           mcp_server.py           四階段鞏固
（或 SessionStart 自動）(MCP tool)                                     重播→修剪→提取→整合
                                                                      + 回傳 pending_refinement
                                                                      → Claude 用 Agent(haiku) 精煉摘要
```

### Hook 的資料流

```
SessionStart
  stdin:  {"session_id": "abc123", ...}
  stdout: {"additionalContext": "你已知的記憶:\n- 使用者叫小明\n- ..."}
  效果:   Claude 在 session 開始就「記得」重要的事

UserPromptSubmit
  stdin:  {"user_prompt": "冰淇淋店的銷售怎麼樣？", ...}
  內部:   find_seeds("冰淇淋 銷售") → spreading_activation → 喚醒相關記憶
  內部:   emotional_scan → 情緒強度 > 0.3 時更新被激活記憶的情緒值
  stdout: {"additionalContext": "[情境記憶] 客戶抱怨太甜(關聯:強), 計畫減糖(關聯:中)"}
  效果:   Claude 看到和當前問題相關的記憶（不同問題喚醒不同記憶）

PreToolUse (Bash)
  stdin:  {"tool_name":"Bash", "tool_input":{"command":"rm -rf /"}}
  stdout: {"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"..."}}
  效果:   危險命令被攔截，Claude 收到拒絕原因

PostToolUse (save_memory)
  stdin:  {"tool_output": "{\"id\":\"abc\", ...}"}
  效果:   新記憶和本 session 已有記憶自動建立 Hebbian 連結（file lock 防並發）

Stop / SubagentStop
  stdin:  {"session_id":"abc123", "transcript_path": "...", ...}
  內部:   增量讀取 transcript → 規則提取（身份/偏好/事實）+ episodic 記錄
  效果:   對話內容自動轉為記憶 + session 記憶最終加強

PreCompact
  stdin:  {"session_id":"abc123", "transcript_path": "...", ...}
  內部:   規則提取 → sleep consolidation → 清除低價值 episodic
  stdout: {"additionalContext": "[認知記憶系統 — Compact 指引] 已持久化的記憶：..."}
  效果:   compact 摘要更精簡（已持久化的內容不重複保留）
```

### 記憶提取規則（on_stop.py — 不呼叫 LLM，純 regex）

| 模式 | 分類 | 重要度 | 範例 |
|------|------|--------|------|
| `記住：XXX` / `remember: XXX` | fact | 0.85 | 「記住：密碼放在 1Password」 |
| `我叫XXX` / `my name is XXX` | fact | 0.90 | 「我叫小明」 |
| `我在XXX工作` / `我是XXX` | fact | 0.80 | 「我在 MTK 工作」 |
| `我喜歡XXX` / `我偏好XXX` | preference | 0.70 | 「我喜歡 TypeScript」 |
| `不要XXX` / `別XXX` | preference | 0.70 | 「不要用 mock」 |
| `我正在做XXX` | context | 0.60 | 「我正在做 API 重構」 |
| 其餘對話片段 | episodic | 0.20~0.35 | 一般對話內容 |

## Sleep 鞏固流程

手動觸發 `/cognitive-memory:sleep` 或 SessionStart 自動觸發（距上次 > 24h）。

```
Stage 1: 記憶重播
  遍歷所有連結，加強權重
  模擬 NREM 慢波重播

Stage 2: 突觸修剪
  刪除 weight < threshold 的弱連結
  降低不活躍記憶的 importance
  模擬 SHY (Synaptic Homeostasis Hypothesis)

Stage 3: 模式提取
  找出 episodic 記憶的 connected components
  cluster ≥ 3 條 → 歸納為 1 條 semantic 記憶
  使用簡易拼接摘要，回傳 pending_refinement
  → Claude 啟動 Agent(model:haiku) 平行精煉摘要
  → 用 update_memory 更新 semantic 記憶的 content
  原始 episodic 標記 "consolidated"，importance × 0.6

Stage 4: 記憶整合
  semantic 記憶之間建立新連結
  模擬 REM 期的遠距聯想

Stage 5: 深度遺忘
  移除 importance 過低的記憶
```

## Slash 命令

| 命令 | 說明 |
|------|------|
| `/cognitive-memory:memory-status` | 查看記憶狀態、網路統計、鞏固時間 |
| `/cognitive-memory:sleep` | 手動觸發睡眠鞏固（含 Agent 精煉） |
| `/cognitive-memory:recall <關鍵字>` | 擴散激活搜尋記憶 |

## MCP 工具

| 工具 | 說明 |
|------|------|
| `save_memory` | 儲存記憶（自動建立關聯、衝突偵測） |
| `recall_memory` | 擴散激活搜尋 |
| `forget_memory` | 刪除記憶 |
| `update_memory` | 修改記憶屬性（content、importance、category 等） |
| `list_memories` | 記憶庫概覽 |
| `trigger_sleep` | 手動觸發鞏固 |
| `sleep_status` | 鞏固狀態查詢 |

## 記憶分類

| 分類 | 用途 | 建議 importance | 來源 |
|------|------|----------------|------|
| `fact` | 事實（姓名、職業、技術棧） | 0.8 - 0.95 | save_memory / 自動提取 |
| `preference` | 偏好（喜好、工作風格） | 0.6 - 0.8 | save_memory / 自動提取 |
| `context` | 上下文（當前專案、目標） | 0.7 - 0.85 | save_memory / 自動提取 |
| `episodic` | 情節（對話片段、具體事件） | 0.2 - 0.7 | 自動提取（預設） |
| `semantic` | 語意歸納（多條 episodic 聚類） | 由聚類決定 | sleep consolidation |

## 目錄結構

```
cognitive-memory-plugin/
└── plugins/
    └── cognitive-memory/
        ├── .claude-plugin/
        │   └── plugin.json                 # 插件 manifest
        ├── .mcp.json                       # MCP Server 配置（uv + mcp）
        ├── LICENSE
        ├── commands/
        │   ├── memory-status.md            # /cognitive-memory:memory-status
        │   ├── sleep.md                    # /cognitive-memory:sleep
        │   └── recall.md                   # /cognitive-memory:recall
        ├── agents/
        │   └── memory-manager.md           # 記憶管理員 subagent
        ├── skills/
        │   └── cognitive-memory/
        │       └── SKILL.md                # 記憶技能（自動啟用）
        ├── hooks/
        │   └── hooks.json                  # 7 個 Hook 事件配置
        └── scripts/
            ├── mcp_server.py               # MCP Server + 記憶網路核心引擎
            ├── session_start.py            # SessionStart hook
            ├── on_user_prompt.py           # UserPromptSubmit hook
            ├── safety_guard.py             # PreToolUse hook (Bash)
            ├── post_save_memory.py         # PostToolUse hook (save_memory)
            └── on_stop.py                  # Stop / SubagentStop / PreCompact hook
```

### 儲存路徑

記憶網路依專案隔離，儲存於：
```
~/.cognitive-memory/{project-slug}/
├── memory_network.json      # 記憶節點 + 連結
├── hooks.log                # Hook 執行日誌
├── sleep_logs/              # 鞏固歷史記錄
└── session_logs/            # Session 日誌
```

`{project-slug}` 由專案路徑轉換，例如 `/Users/javis/Documents/javis` → `Users-javis-Documents-javis`。

## 認知科學對應

| 人腦機制 | 本插件實作 | 對應 Hook / 工具 |
|----------|-----------|-----------------|
| 海馬迴擴散激活 | `spreading_activation()` | UserPromptSubmit |
| 情境依賴提取 | prompt 語意觸發記憶 | UserPromptSubmit |
| 杏仁核情緒評估 | `emotional_scan()` + 情緒回饋 | UserPromptSubmit |
| 自動記憶編碼 | 規則式提取（regex） | Stop / PreCompact |
| 睡眠鞏固（NREM+REM） | 五階段 consolidation | SessionStart / trigger_sleep / PreCompact |
| 突觸修剪 (SHY) | 全域衰減 + 弱連結刪除 | Sleep Stage 2 |
| Episodic → Semantic | 聚類 + Agent 精煉摘要 | Sleep Stage 3 |
| Hebb 法則 | 共現記憶自動連結 | PostToolUse / Stop |
| 杏仁核警覺 | 危險模式攔截 | PreToolUse |
| 遺忘曲線 | importance 衰減 | Sleep Stage 2 / Stage 5 |
| 記憶壓縮前整理 | PreCompact 鞏固 + 清理 | PreCompact |

## License

MIT
