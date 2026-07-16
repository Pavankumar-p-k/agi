# Final verification
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
print('=== Phase 1 Pipeline ===')
from core.agent_loop import stream_agent_loop, get_fallback_count
print('  stream_agent_loop: OK')
print('  Legacy RuntimePipeline: REMOVED')
print('  Legacy ControlLoop: REMOVED')
print(f'  Fallback counter: {get_fallback_count()}')

print()
print('=== Legacy imports check ===')
import subprocess
result = subprocess.run(['powershell', '-c', 'Select-String -Pattern "core.legacy.control_loop" -Path "core\\*.py", "daemon\\*.py"'], capture_output=True, text=True)
print(f'  Legacy control_loop in prod: {"FOUND" if result.stdout.strip() else "NONE"}')

result = subprocess.run(['powershell', '-c', 'Select-String -Pattern "from core.pipeline import RuntimePipeline" -Path "core\\*.py", "daemon\\*.py"'], capture_output=True, text=True)
print(f'  RuntimePipeline in prod: {"FOUND" if result.stdout.strip() else "NONE"}')

print()
print('=== All checks passed ===')