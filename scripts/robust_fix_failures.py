import os
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def robust_fix_file(file_path):
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

    # Regex for except Exception as e:     logger.warning(f"[SWALLOWED] {e}") or except Exception as e:     logger.warning(f"[SWALLOWED] {e}")
    # Handles indentation and possible comments
    # Pattern 1: except Exception as e:     logger.warning(f"[SWALLOWED] {e}")
    pattern1 = re.compile(r'(\s+)except:\s*pass', re.MULTILINE)
    # Pattern 2: except Exception as e:     logger.warning(f"[SWALLOWED] {e}")
    pattern2 = re.compile(r'(\s+)except\s+Exception:\s*pass', re.MULTILINE)
    # Pattern 3: except Exception as e:     logger.warning(f"[SWALLOWED] {e}")
    pattern3 = re.compile(r'(\s+)except\s+Exception\s+as\s+(\w+):\s*pass', re.MULTILINE)

    new_content = content
    
    # Replacement logic
    # We want to change 'pass' to a logger call. 
    # We need to ensure 'logger' is available.
    
    replacements = 0
    
    def repl1(match):
        indent = match.group(1)
        return f"{indent}except Exception as e:{indent}    logger.warning(f\"[SWALLOWED] {{e}}\")"

    def repl2(match):
        indent = match.group(1)
        return f"{indent}except Exception as e:{indent}    logger.warning(f\"[SWALLOWED] {{e}}\")"

    def repl3(match):
        indent = match.group(1)
        e_var = match.group(2)
        return f"{indent}except Exception as {e_var}:{indent}    logger.warning(f\"[SWALLOWED] {{{e_var}}}\")"

    temp_content = pattern1.sub(repl1, new_content)
    if temp_content != new_content:
        replacements += 1
        new_content = temp_content
        
    temp_content = pattern2.sub(repl2, new_content)
    if temp_content != new_content:
        replacements += 1
        new_content = temp_content
        
    temp_content = pattern3.sub(repl3, new_content)
    if temp_content != new_content:
        replacements += 1
        new_content = temp_content

    if replacements > 0:
        # Check for logger
        if 'import logging' not in new_content:
            new_content = "import logging\n" + new_content
        if 'logger = logging.getLogger' not in new_content and 'logger = logging.getChild' not in new_content:
            # Insert after imports
            lines = new_content.splitlines(keepends=True)
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    insert_idx = i + 1
            lines.insert(insert_idx, "logger = logging.getLogger(__name__)\n")
            new_content = "".join(lines)
            
        file_path.write_text(new_content, encoding='utf-8')
        return True
    return False

def main():
    root_dir = Path('.')
    fixed_count = 0
    for py_file in root_dir.glob('**/*.py'):
        if 'venv' in str(py_file) or '.venv' in str(py_file) or '__pycache__' in str(py_file):
            continue
        if robust_fix_file(py_file):
            print(f"Fixed {py_file}")
            fixed_count += 1
    print(f"Total files fixed: {fixed_count}")

if __name__ == "__main__":
    main()
