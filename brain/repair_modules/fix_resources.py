"""brain/repair_modules/fix_resources.py
Deterministic Android resource repair.
Creates missing drawable/color/string resources.
"""
import re
from pathlib import Path


VECTOR_DRAWABLE_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp"
    android:height="24dp"
    android:viewportWidth="24"
    android:viewportHeight="24">
    <path
        android:fillColor="#FF000000"
        android:pathData="M12,2C6.48,2 2,6.48 2,12s4.48,10 10,10 10,-4.48 10,-10S17.52,2 12,2z" />
</vector>
"""


def fix_resources(project_dir: str, errors: list[dict]) -> list[str]:
    """Create missing drawable, color, and string resources."""
    created = []
    res_dir = Path(project_dir) / "app" / "src" / "main" / "res"

    for error in errors:
        msg = error.get("message", "")

        drawable_match = re.search(r"@drawable/(\w+)", msg)
        if drawable_match:
            name = drawable_match.group(1)
            drawable_dir = res_dir / "drawable"
            drawable_dir.mkdir(parents=True, exist_ok=True)
            path = drawable_dir / f"{name}.xml"
            if not path.exists():
                path.write_text(VECTOR_DRAWABLE_TEMPLATE, encoding="utf-8")
                created.append(str(path))

        color_match = re.search(r"@color/(\w+)", msg)
        if color_match:
            name = color_match.group(1)
            values_dir = res_dir / "values"
            values_dir.mkdir(parents=True, exist_ok=True)
            colors_path = values_dir / "colors.xml"
            if colors_path.exists():
                content = colors_path.read_text(encoding="utf-8")
            else:
                content = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n</resources>\n'
            if name not in content:
                content = content.replace("</resources>", f'    <color name="{name}">#FF6200EE</color>\n</resources>')
                colors_path.write_text(content, encoding="utf-8")
                created.append(str(colors_path))

        string_match = re.search(r"@string/(\w+)", msg)
        if string_match:
            name = string_match.group(1)
            values_dir = res_dir / "values"
            values_dir.mkdir(parents=True, exist_ok=True)
            strings_path = values_dir / "strings.xml"
            if strings_path.exists():
                content = strings_path.read_text(encoding="utf-8")
            else:
                content = '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">App</string>\n</resources>\n'
            if name not in content:
                content = content.replace("</resources>", f'    <string name="{name}">{name}</string>\n</resources>')
                strings_path.write_text(content, encoding="utf-8")
                created.append(str(strings_path))

    return created
