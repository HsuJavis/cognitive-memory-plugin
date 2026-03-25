# 🧠 Cognitive Memory Plugin for Claude Code

模擬人類認知記憶機制的 Claude Code 插件。

## 特性

- **擴散激活搜尋** — 記憶以網路形式儲存，搜尋時沿著關聯連結擴散
- **睡眠鞏固** — 週期性整理：重播加強、突觸修剪、模式提取、記憶整合
- **情境觸發** — 不是預載入所有記憶，而是被當前 prompt 的語意喚醒
- **Hebbian Learning** — 同次 session 中存的記憶自動建立連結
- **情緒標記** — 情緒越強烈的記憶越不容易被遺忘
- **安全守衛** — PreToolUse hook 攔截危險 Bash 命令

## 安裝

```bash
# 依賴
pip install mcp anthropic

# 在 Claude Code 中（GitHub 安裝）
/plugin install https://github.com/HsuJavis/cognitive-memory-plugin

# 或本地安裝
/plugin install /path/to/cognitive-memory-plugin
```

安裝後重啟 Claude Code，用 `/mcp` 確認 `cognitive-memory` server 已連線。

## Hook 映射 — 認知機制 × Claude Code 原生事件

這是本插件的核心設計：把人類認知的每個階段映射到 Claude Code 的原生 Hook 事件。

```
人類認知              Claude Code Hook        腳本                    做什麼
────────────────────────────────────────────────────────────────────────────────
起床（記憶已整理好）  SessionStart            session_start.py        睡眠鞏固檢查（>24h 自動執行）
                                                                      + 注入高重要度記憶 (additionalContext)

情境觸發記憶          UserPromptSubmit        on_user_prompt.py       用 prompt 語意做擴散激活
（看到冰淇淋想到小明）                                                + 注入情境記憶 (additionalContext)
                                                                      + System 1 情緒快速掃描

杏仁核警覺            PreToolUse (Bash)       safety_guard.py         偵測危險命令模式
（危險！快閃）                                                         → permissionDecision: "deny"

Hebb 法則             PostToolUse             post_save_memory.py     save_memory 後自動連結
（一起激活=一起連結）  (save_memory)                                   本次 session 的記憶互相加強

白天結束標記          Stop / SubagentStop     on_stop.py              最終 Hebbian 加強
（海馬迴標記重要事件）                                                 + 記錄 session 日誌
                                                                      + 清理臨時檔案

睡覺整理              trigger_sleep (MCP tool) mcp_server.py          四階段鞏固
（或 SessionStart 自動）                                               重播→修剪→提取→整合
```

### Hook 的資料流

```
SessionStart
  stdin:  {"session_id": "abc123", ...}
  stdout: {"additionalContext": "你已知的記憶:\n- 使用者叫小明\n- ..."}
  效果:   Claude 在 session 開始就「記得」重要的事

UserPromptSubmit
  stdin:  {"message": {"role":"user", "content":"冰淇淋店的銷售怎麼樣？"}}
  內部:   find_seeds("冰淇淋 銷售") → spreading_activation → 喚醒相關記憶
  stdout: {"additionalContext": "[情境記憶] 客戶抱怨太甜(關聯:強), 計畫減糖(關聯:中)"}
  效果:   Claude 看到和當前問題相關的記憶（不同問題喚醒不同記憶）

PreToolUse (Bash)
  stdin:  {"tool_name":"Bash", "tool_input":{"command":"rm -rf /"}}
  stdout: {"hookSpecificOutput":{"permissionDecision":"deny","permissionDecisionReason":"..."}}
  效果:   危險命令被攔截，Claude 收到拒絕原因

PostToolUse (save_memory)
  stdin:  {"tool_output": "{\"id\":\"abc\", ...}"}
  效果:   新記憶和本 session 已有記憶自動建立 Hebbian 連結

Stop
  stdin:  {"session_id":"abc123", "stop_hook_active": false}
  效果:   session 記憶最終加強 + 記錄日誌供鞏固用
```

## Slash 命令

| 命令 | 說明 |
|------|------|
| `/cognitive-memory:memory-status` | 查看記憶狀態 |
| `/cognitive-memory:sleep` | 手動觸發睡眠鞏固 |
| `/cognitive-memory:recall <關鍵字>` | 擴散激活搜尋記憶 |

## MCP 工具

| 工具 | 說明 |
|------|------|
| `save_memory` | 儲存記憶（自動建立關聯）|
| `recall_memory` | 擴散激活搜尋 |
| `forget_memory` | 刪除記憶 |
| `list_memories` | 記憶庫概覽 |
| `trigger_sleep` | 手動觸發鞏固 |
| `sleep_status` | 鞏固狀態查詢 |

## 目錄結構

```
cognitive-memory-plugin/
├── .claude-plugin/
│   └── plugin.json                 # 插件 manifest
├── .mcp.json                       # MCP Server 配置 → scripts/mcp_server.py
├── commands/
│   ├── memory-status.md            # /memory-status
│   ├── sleep.md                    # /sleep
│   └── recall.md                   # /recall
├── agents/
│   └── memory-manager.md           # 記憶管理員 subagent
├── skills/
│   └── cognitive-memory/
│       └── SKILL.md                # 記憶技能（Claude 自動啟用）
├── hooks/
│   └── hooks.json                  # 6 個 Hook 事件配置
├── scripts/
│   ├── mcp_server.py               # MCP Server（自包含核心引擎）
│   ├── session_start.py            # SessionStart hook
│   ├── on_user_prompt.py           # UserPromptSubmit hook
│   ├── safety_guard.py             # PreToolUse hook
│   ├── post_save_memory.py         # PostToolUse hook
│   └── on_stop.py                  # Stop / SubagentStop hook
└── README.md
```

## 認知科學對應

| 人腦機制 | 本插件實作 | 對應 Hook |
|----------|-----------|-----------|
| 海馬迴擴散激活 | `spreading_activation()` | UserPromptSubmit |
| 情境依賴提取 | prompt 語意觸發記憶 | UserPromptSubmit |
| 杏仁核情緒評估 | `emotional_scan()` | UserPromptSubmit |
| 睡眠鞏固（NREM+REM）| 四階段 consolidation | SessionStart / trigger_sleep |
| 突觸修剪 (SHY) | 全域衰減 + 弱連結刪除 | SessionStart (自動) |
| Episodic → Semantic | 聚類 + 模式提取 | SessionStart (自動) |
| Hebb 法則 | 共現記憶自動連結 | PostToolUse / Stop |
| 杏仁核警覺 | 危險模式攔截 | PreToolUse |
| 遺忘曲線 | importance × 0.95/cycle | SessionStart (鞏固時) |

## License

MIT
