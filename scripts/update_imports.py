import os
import re

# Mapping of old imports to new imports
MAPPING = {
    r'from ai_os\.event_bus import': 'from core.event_bus import',
    r'import ai_os\.event_bus': 'import core.event_bus',
    r'from ai_os\.docker_sandbox import': 'from core.sandbox.docker_sandbox import',
    r'from ai_os\.sandbox import': 'from core.sandbox.sandbox import',
    r'from ai_os\.sandbox_manager import': 'from core.sandbox.sandbox_manager import',
    r'from api\.server import': 'from core.main import',
}

def update_imports(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    new_content = content
    for old, new in MAPPING.items():
        new_content = re.sub(old, new, new_content)

    if new_content != content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated imports in {file_path}")

def main():
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['venv', '.venv', '__pycache__', 'node_modules', '.git']):
            continue
        for file in files:
            if file.endswith('.py'):
                update_imports(os.path.join(root, file))

if __name__ == "__main__":
    main()
