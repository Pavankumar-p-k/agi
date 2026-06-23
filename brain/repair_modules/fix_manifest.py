"""brain/repair_modules/fix_manifest.py
Deterministic AndroidManifest.xml repair.
Adds missing activity declarations, application block, permissions.
"""
import re
import xml.etree.ElementTree as ET


def fix_manifest(manifest_path: str, errors: list[dict]) -> bool:
    """Fix AndroidManifest.xml based on compilation errors."""
    try:
        ET.parse(manifest_path)
    except (ET.ParseError, FileNotFoundError):
        return False

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return False

    changed = False
    for error in errors:
        if "Activity" in error.get("symbol", "") and "declared" in error.get("message", ""):
            activity_name = error.get("symbol", "").replace("class ", "").strip()
            if activity_name and f"android:name=\".{activity_name}\"" not in content:
                activity_tag = f'<activity android:name=".{activity_name}" />'
                content = content.replace("</application>", f"    {activity_tag}\n        </application>")
                changed = True

        if "uses-permission" in error.get("message", ""):
            perm = error.get("symbol", "")
            if perm and f"android.permission.{perm}" not in content:
                perm_tag = f'<uses-permission android:name="android.permission.{perm}" />'
                content = content.replace("<application", f"{perm_tag}\n    <application")
                changed = True

    if changed:
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(content)
    return changed
