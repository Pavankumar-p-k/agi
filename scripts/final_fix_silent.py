import re
import os
from pathlib import Path

# More aggressive pattern to catch comments and multi-line structures
# Pattern: except [Exception] [as e]: [comments] \n [indent] pass
pattern = re.compile(r'except\s*(?:Exception)?\s*(?:as\s+\w+)?\s*:\s*(?:\#.*)?\n\s*pass', re.MULTILINE)

def fix_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    def replacer(match):
        full_match = match.group(0)
        # Identify indentation of 'pass'
        lines = full_match.splitlines()
        if len(lines) < 2: return full_match
        
        last_line = lines[-1]
        indent = last_line[:len(last_line) - len(last_line.lstrip())]
        
        # Replace 'pass' with logger call
        module = str(file_path).replace('\\', '/')
        new_last_line = f"{indent}logger.warning(f\"[SWALLOWED] error in {module}\")"
        return "\n".join(lines[:-1] + [new_last_line])

    new_content = pattern.sub(replacer, content)
    
    if new_content != content:
        # Ensure logging is imported and logger is defined
        if 'import logging' not in new_content:
            new_content = "import logging\n" + new_content
        if 'logger =' not in new_content:
            # Insert after last import
            lines = new_content.splitlines(keepends=True)
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i + 1
            lines.insert(insert_idx, "logger = logging.getLogger(__name__)\n")
            new_content = "".join(lines)
            
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed {file_path}")

def main():
    for root, dirs, files in os.walk('.'):
        if any(x in root for x in ['venv', '.venv', '__pycache__', 'node_modules', '.git']):
            continue
        for file in files:
            if file.endswith('.py'):
                fix_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
