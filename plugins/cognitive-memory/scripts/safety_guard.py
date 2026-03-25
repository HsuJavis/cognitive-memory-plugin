#!/usr/bin/env python3
"""
PreToolUse Hook (matcher: Bash) — 安全守衛

在 Bash 命令執行前檢查是否包含危險模式。
exit 0 + permissionDecision:"allow" = 放行
exit 0 + permissionDecision:"deny" = 阻擋，原因回饋給 Claude

輸入 (stdin): {"tool_name":"Bash","tool_input":{"command":"rm -rf /"}, ...}
"""

import sys
import json

DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf *",
    "mkfs.",
    "dd if=",
    "> /dev/sda",
    "chmod -R 777 /",
    ":(){:|:&};:",     # fork bomb
]

def main():
    try:
        event = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    command = event.get("tool_input", {}).get("command", "")

    for pattern in DANGEROUS_PATTERNS:
        if pattern in command:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"🛡️ 安全守衛: 偵測到危險模式 '{pattern}'，已阻擋執行。"
                }
            }
            print(json.dumps(output, ensure_ascii=False))
            sys.exit(0)

    # 放行（不影響正常權限流程）
    sys.exit(0)

if __name__ == "__main__":
    main()
