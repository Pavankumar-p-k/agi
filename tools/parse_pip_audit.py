# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
