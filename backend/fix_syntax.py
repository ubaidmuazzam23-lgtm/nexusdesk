#!/usr/bin/env python3
import re, py_compile, tempfile, os

path = "app/services/chat_service.py"
with open(path) as f:
    src = f.read()

# Fix the broken strip line with escaped quotes
broken_patterns = [
    ("strip()' in line", None),
]

lines = src.split('\n')
fixed_lines = []
fixed_count = 0

for i, line in enumerate(lines):
    # Find line with mangled strip quotes near clean_title in _create_ai_resolved_ticket
    if 'clean_title' in line and 'strip' in line and ('\\' in line or line.count("'") > 4 or line.count('"') > 4):
        fixed_lines.append("            clean_title = title_resp.content[0].text.strip().strip('\"').strip(\"'\")")
        fixed_count += 1
        print(f"Fixed line {i+1}: {line[:80]}...")
    else:
        fixed_lines.append(line)

src = '\n'.join(fixed_lines)

with open(path, 'w') as f:
    f.write(src)

# Verify
tmp = tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w')
tmp.write(src)
tmp.close()
try:
    py_compile.compile(tmp.name, doraise=True)
    print(f"\n✓ Syntax OK — {fixed_count} line(s) fixed. Ready to start.")
except py_compile.PyCompileError as e:
    print(f"\n✗ Still broken: {e}")
finally:
    os.unlink(tmp.name)