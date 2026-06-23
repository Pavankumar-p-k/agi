"""brain/repair_modules/fix_layouts.py
Deterministic XML layout repair.
Creates missing layout files, adds missing IDs, fixes XML attributes.
"""
import re
from pathlib import Path


LAYOUT_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical">

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="Placeholder" />

</LinearLayout>
"""


def fix_layouts(project_dir: str, errors: list[dict]) -> list[str]:
    """Create missing layout files and add missing IDs."""
    created = []
    for error in errors:
        msg = error.get("message", "")
        # R.layout.X not found
        match = re.search(r"R\.layout\.(\w+)", msg)
        if match:
            layout_name = match.group(1)
            layout_path = Path(project_dir) / "app" / "src" / "main" / "res" / "layout" / f"{layout_name}.xml"
            if not layout_path.exists():
                layout_path.parent.mkdir(parents=True, exist_ok=True)
                layout_path.write_text(LAYOUT_TEMPLATE, encoding="utf-8")
                created.append(str(layout_path))

        # R.id.X not found
        id_match = re.search(r"R\.id\.(\w+)", msg)
        if id_match:
            id_name = id_match.group(1)
            layout_dir = Path(project_dir) / "app" / "src" / "main" / "res" / "layout"
            if layout_dir.exists():
                for xml_file in layout_dir.glob("*.xml"):
                    content = xml_file.read_text(encoding="utf-8")
                    if f"@+id/{id_name}" not in content:
                        view_tag = f'<TextView\n        android:id="@+id/{id_name}"\n        android:layout_width="wrap_content"\n        android:layout_height="wrap_content" />\n'
                        content = content.replace("</LinearLayout>", f"    {view_tag}</LinearLayout>")
                        xml_file.write_text(content, encoding="utf-8")
                        created.append(str(xml_file))
                        break
    return created
