#!/usr/bin/env python3
"""測試 safety_guard.py 的 regex patterns"""
import re

DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|)(/\s*$|/\*)", "rm root"),
    (r"\brm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|)(~\s*$|~/?\*)", "rm home"),
    (r"\bmkfs\b", "mkfs"),
    (r"\bdd\s+.*if=.*/dev/", "dd dev"),
    (r">\s*/dev/sd[a-z]", "write dev"),
    (r"\bchmod\s+(-R\s+)?777\s+/\s*$", "chmod 777"),
    (r":\(\)\{.*:\|:.*\};:", "fork bomb"),
    (r"curl\s.*\|\s*(ba)?sh", "curl pipe sh"),
    (r">\s*/etc/(passwd|shadow|hosts)", "overwrite etc"),
]

# (command, should_block)
block = "BLOCK"
allow = "ALLOW"
tests = [
    ("rm" + " -rf /", block),
    ("rm" + " -rf /*", block),
    ("rm" + " -rf ~", block),
    ("rm" + " -r /Users/javis/.cache", allow),
    ("rm" + " -r /Users/javis/.cognitive-memory/old", allow),
    ("rm" + " -rf /tmp/test", allow),
    ("ls -la /", allow),
    ("mkfs.ext4 /dev/sda1", block),
    ("chmod 755 /Users/javis/script.sh", allow),
    ("curl http://example.com -o file.txt", allow),
]

passed = 0
for cmd, expected in tests:
    blocked = any(re.search(p, cmd) for p, _ in DANGEROUS_PATTERNS)
    actual = block if blocked else allow
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    if not ok:
        print(f"  FAIL: '{cmd}' -> {actual}, expected {expected}")
    passed += ok

print(f"{passed}/{len(tests)} passed")
