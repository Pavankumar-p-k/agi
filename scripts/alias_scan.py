import pathlib
import re

root = pathlib.Path(r'c:\Users\peter\Desktop\jarvis')
aliases = ['ai_os','core','api','cognitive_agent','autonomy','tools','learning','memory','models','orchestrator','gpu']
pattern = re.compile(rf'^(?:from|import)\s+({'|'.join(re.escape(a) for a in aliases)})\b')

for path in sorted(root.rglob('*.py')):
    if 'backend' not in path.parts:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    for i, line in enumerate(text.splitlines(), 1):
        if pattern.search(line):
            print(f"{path.relative_to(root)}:{i}: {line.strip()}")
            break
