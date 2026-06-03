import json
from pathlib import Path
p = Path('pip_audit_report.json')
if not p.exists():
    print('pip_audit_report.json not found')
    raise SystemExit(1)

j = json.loads(p.read_text(encoding='utf-8'))
v = [dep for dep in j.get('dependencies', []) if dep.get('vulns')]
print('vulnerable_count:', len(v))
for d in v:
    ids = [vul.get('id') for vul in d['vulns']]
    fixes = [vul.get('fix_versions') for vul in d['vulns']]
    print(f"{d['name']} {d['version']} -> {len(d['vulns'])} vulns; ids={ids}; fixes={fixes}")

# Also print top critical ones (heuristic: many vulns or no fixes)
print('\nTop items needing attention:')
for d in sorted(v, key=lambda x: (len(x['vulns']), 0 if any(v.get('fix_versions') for v in x['vulns']) else 1), reverse=True)[:20]:
    print(f"- {d['name']} {d['version']}: {len(d['vulns'])} vulns; fixes={[v.get('fix_versions') for v in d['vulns']]}")
