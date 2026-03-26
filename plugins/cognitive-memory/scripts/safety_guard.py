#!/usr/bin/env python3
"""
PreToolUse Hook (matcher: Bash) — 安全守衛

在 Bash 命令執行前檢查是否包含危險模式。
exit 0 + permissionDecision:"deny" = 阻擋，原因回饋給 Claude
exit 0 (無輸出) = 放行

輸入 (stdin): {"tool_name":"Bash","tool_input":{"command":"rm -rf /"}, ...}
"""

import sys
import json
import re

# 危險模式: (regex pattern, 說明)
# 用 regex 精確匹配，避免 "rm -rf /Users/..." 被誤判為 "rm -rf /"
DANGEROUS_PATTERNS = [
    # rm -rf / 或 rm -rf /* （但不匹配 rm -rf /some/path）
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|)(/\s*$|/\*)", "rm -rf / (刪除根目錄)"),
    # rm -rf ~ 或 rm -rf ~/*
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|)(~\s*$|~/?\*)", "rm -rf ~ (刪除家目錄)"),
    # mkfs (格式化磁碟)
    (r"\bmkfs\b", "mkfs (格式化磁碟)"),
    # dd if= 寫入磁碟設備
    (r"\bdd\s+.*if=.*/dev/", "dd 寫入磁碟設備"),
    # 直接寫入磁碟設備
    (r">\s*/dev/sd[a-z]", "直接寫入磁碟設備"),
    # chmod -R 777 / （但不匹配 chmod -R 777 /some/path）
    (r"\bchmod\s+(-R\s+)?777\s+/\s*$", "chmod 777 / (全域權限變更)"),
    # fork bomb
    (r":\(\)\{.*:\|:.*\};:", "fork bomb"),
    # 危險的 curl | sh 模式
    (r"curl\s.*\|\s*(ba)?sh", "curl pipe to shell (可能執行未知腳本)"),
    # 清空重要系統檔案
    (r">\s*/etc/(passwd|shadow|hosts)", "覆寫系統檔案"),
]


def main():
    try:
        event = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    command = event.get("tool_input", {}).get("command", "")
    if not command:
        sys.exit(0)

    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"🛡️ 安全守衛: {description}",
                }
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(0)

    # 放行
    sys.exit(0)

if __name__ == "__main__":
    main()
