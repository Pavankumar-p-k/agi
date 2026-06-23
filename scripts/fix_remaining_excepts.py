import logging
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
"""Fix remaining except Exception as e:     logger.warning(f"[SWALLOWED] {e}") blocks missed by initial batch."""
import re
logger = logging.getLogger(__name__)

fixes = {
    'tests/unit/test_ssrf_fuzz.py': [(146, 'ssrf_fuzz_cleanup')],
    'tools/jarvis_website_cli.py': [(175, 'website_cli_operation')],
    'mcp/email_server.py': [(214, 'fetch_email'), (273, 'send_email'), (494, 'handle_webhook'), (1517, 'email_scheduler')],
    'mcp/memory_server.py': [(148, 'recall_memory'), (173, 'delete_memory')],
    'mcp/rag_server.py': [(127, 'query_rag')],
}

for rel_path, instances in fixes.items():
    with open(rel_path, encoding='utf-8') as f:
        text = f.read()
    lines = text.split('\n')
    modified = False
    for line_no, context in instances:
        idx = line_no - 1
        if idx >= len(lines):
            print(f'{rel_path}:{line_no} out of range')
            continue
        if not lines[idx].strip().startswith('except'):
            print(f'{rel_path}:{line_no} not an except line: {lines[idx].strip()!r}')
            continue
        if 'as e' not in lines[idx] and 'as ' not in lines[idx]:
            lines[idx] = lines[idx].rstrip() + ' as e'
        for j in range(idx + 1, min(idx + 3, len(lines))):
            if lines[j].strip() == 'pass':
                indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                mod_path = rel_path.replace('/', '.').replace('\\', '.').rstrip('.py')
                lines[j] = f'{indent}logger.warning("[{mod_path}] {context} failed: %s", e)'
                modified = True
                break
    if modified:
        with open(rel_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f'Fixed {rel_path} ({len(instances)} instances)')
    else:
        print(f'No changes in {rel_path}')
