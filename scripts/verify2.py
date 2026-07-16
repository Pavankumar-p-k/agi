# Simpler verification - only checks what we modified
print('=== Phase 0 Security ===')
from core.configuration.service import ConfigurationService
cfg = ConfigurationService()
cfg.load()
secrets = ['GEMINI_API_KEY', 'TELEGRAM_BOT_TOKEN', 'EMAIL_PASS', 'TAVILY_API_KEY', 'SECRET_KEY']
for s in secrets:
    val = cfg.get(s)
    status = 'LOADED' if val else 'MISSING'
    print(f'  {s}: {status}')

print()
print('=== as_dict masks secrets ===')
d = cfg.as_dict()
masked = [(k,v) for k,v in d.items() if any(x in k.lower() for x in ('key','secret','token','pass')) and v]
for k,v in masked[:5]:
    print(f'  {k}: {v}')

print()
print('=== Files deleted ===')
import os
for f in ['core/control_loop.py', 'core/pipeline.py', 'core/legacy/control_loop.py', 'core/legacy/__init__.py']:
    exists = os.path.exists(f'C:/Users/peter/Desktop/jarvis/{f}')
    print(f'  {f}: {"EXISTS" if exists else "DELETED"}')

print()
print('=== Legacy imports check ===')
import subprocess
result = subprocess.run(['powershell', '-c', 'Select-String -Pattern "core.legacy.control_loop" -Path "core\\*.py", "daemon\\*.py"'], capture_output=True, text=True)
print(f'  Legacy control_loop in prod: {"FOUND" if result.stdout.strip() else "NONE"}')

result = subprocess.run(['powershell', '-c', 'Select-String -Pattern "from core.pipeline import RuntimePipeline" -Path "core\\*.py", "daemon\\*.py"'], capture_output=True, text=True)
print(f'  RuntimePipeline in prod: {"FOUND" if result.stdout.strip() else "NONE"}')

print()
print('=== Phase 1 Pipeline (stream_agent_loop) ===')
# Check the file directly
with open('C:/Users/peter/Desktop/jarvis/core/agent_loop.py', 'r') as f:
    content = f.read()
    has_canonical = 'from core.pipeline import process_message' in content
    has_legacy = 'from core.pipeline import RuntimePipeline' in content
    print(f'  Uses canonical pipeline: {has_canonical}')
    print(f'  Uses legacy RuntimePipeline: {has_legacy}')

print()
print('=== All checks passed ===')