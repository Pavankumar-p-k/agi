"""brain/repair_modules/fix_imports.py
Deterministic import repair.
Adds missing imports, resolves import-name collisions.
"""
import re

KNOWN_ANDROID_IMPORTS: dict[str, str] = {
    "Gson": "com.google.gson.Gson",
    "GsonBuilder": "com.google.gson.GsonBuilder",
    "JsonObject": "com.google.gson.JsonObject",
    "JsonArray": "com.google.gson.JsonArray",
    "TypeToken": "com.google.gson.reflect.TypeToken",
    "Retrofit": "retrofit2.Retrofit",
    "RecyclerView": "androidx.recyclerview.widget.RecyclerView",
    "LinearLayoutManager": "androidx.recyclerview.widget.LinearLayoutManager",
    "LiveData": "androidx.lifecycle.LiveData",
    "ViewModel": "androidx.lifecycle.ViewModel",
    "ViewModelProvider": "androidx.lifecycle.ViewModelProvider",
    "AndroidViewModel": "androidx.lifecycle.AndroidViewModel",
    "MutableLiveData": "androidx.lifecycle.MutableLiveData",
    "Room": "androidx.room.Room",
    "Database": "androidx.room.Database",
    "Dao": "androidx.room.Dao",
    "Entity": "androidx.room.Entity",
    "PrimaryKey": "androidx.room.PrimaryKey",
    "Insert": "androidx.room.Insert",
    "Update": "androidx.room.Update",
    "Delete": "androidx.room.Delete",
    "Query": "androidx.room.Query",
    "TypeConverters": "androidx.room.TypeConverters",
    "Navigation": "androidx.navigation.Navigation",
    "NavController": "androidx.navigation.NavController",
    "NavHostFragment": "androidx.navigation.fragment.NavHostFragment",
    "NavGraph": "androidx.navigation.NavGraph",
    "Bundle": "android.os.Bundle",
    "Parcelable": "android.os.Parcelable",
    "Intent": "android.content.Intent",
    "SharedPreferences": "android.content.SharedPreferences",
    "AppCompatTextView": "androidx.appcompat.widget.AppCompatTextView",
    "AppCompatButton": "androidx.appcompat.widget.AppCompatButton",
    "AppCompatEditText": "androidx.appcompat.widget.AppCompatEditText",
    "AppCompatImageView": "androidx.appcompat.widget.AppCompatImageView",
    "MaterialButton": "com.google.android.material.button.MaterialButton",
    "MaterialTextView": "com.google.android.material.textview.MaterialTextView",
    "MaterialCardView": "com.google.android.material.card.MaterialCardView",
    "BottomNavigationView": "com.google.android.material.bottomnavigation.BottomNavigationView",
    "ViewPager2": "androidx.viewpager2.widget.ViewPager2",
    "ViewPager": "androidx.viewpager.widget.ViewPager",
    "FragmentStateAdapter": "androidx.viewpager2.adapter.FragmentStateAdapter",
    "FragmentPagerAdapter": "androidx.fragment.app.FragmentPagerAdapter",
    "ListView": "android.widget.ListView",
    "ArrayAdapter": "android.widget.ArrayAdapter",
    "BaseAdapter": "android.widget.BaseAdapter",
    "List": "java.util.List",
    "ArrayList": "java.util.ArrayList",
    "Map": "java.util.Map",
    "HashMap": "java.util.HashMap",
    "Set": "java.util.Set",
    "HashSet": "java.util.HashSet",
    "UUID": "java.util.UUID",
    "Date": "java.util.Date",
    "Collections": "java.util.Collections",
    "Executor": "java.util.concurrent.Executor",
    "Executors": "java.util.concurrent.Executors",
    "Toast": "android.widget.Toast",
    "Runnable": "java.lang.Runnable",
    "Callable": "java.util.concurrent.Callable",
    "Optional": "java.util.Optional",
    "ContextCompat": "androidx.core.content.ContextCompat",
    "ActivityCompat": "androidx.core.app.ActivityCompat",
    "Context": "android.content.Context",
    "Log": "android.util.Log",
    "TextUtils": "android.text.TextUtils",
    "SpannableString": "android.text.SpannableString",
    "Html": "android.text.Html",
    "Color": "android.graphics.Color",
    "Bitmap": "android.graphics.Bitmap",
    "BitmapFactory": "android.graphics.BitmapFactory",
    "Drawable": "android.graphics.drawable.Drawable",
    "ColorDrawable": "android.graphics.drawable.ColorDrawable",
    "ColorStateList": "android.content.res.ColorStateList",
    "Handler": "android.os.Handler",
    "Looper": "android.os.Looper",
    "AsyncTask": "android.os.AsyncTask",
    "Environment": "android.os.Environment",
    "Vibrator": "android.os.Vibrator",
}

IMPORT_PATTERN = re.compile(r'^import\s+[\w.]+\s*;\s*$', re.MULTILINE)


def fix_imports(java_code: str, errors: list[dict]) -> str:
    """Add missing imports for symbols referenced but not imported."""
    lines = java_code.split("\n")
    existing_imports = set()
    package_line = ""
    insert_line = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("package "):
            package_line = stripped
            insert_line = i + 1
        elif IMPORT_PATTERN.match(stripped):
            existing_imports.add(stripped.rstrip(";").replace("import ", "").strip())
            insert_line = i + 1

    added = set()
    for error in errors:
        symbol = error.get("symbol", "")
        if not symbol:
            continue
        full_import = KNOWN_ANDROID_IMPORTS.get(symbol)
        if full_import and full_import not in existing_imports:
            lines.insert(insert_line, f"import {full_import};")
            existing_imports.add(full_import)
            added.add(symbol)
            insert_line += 1

    for line in lines:
        stripped = line.strip()
        if IMPORT_PATTERN.match(stripped):
            continue
        if stripped.startswith("package ") or stripped == "" or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            continue
        break

    if added:
        import logging
        logging.getLogger(__name__).info(f"[fix_imports] Added {len(added)} imports: {', '.join(sorted(added))}")

    return "\n".join(lines)


def fix_class_names(java_code: str, errors: list[dict]) -> str:
    """Rename class to match filename or rename file to match class name."""
    for error in errors:
        if "class " in java_code and error.get("category") == "class_name_mismatch":
            expected = error.get("expected", "")
            found = error.get("symbol", "")
            if expected and found:
                java_code = java_code.replace(f"class {found}", f"class {expected}")
    return java_code


def fix_package_names(java_code: str, expected_package: str) -> str:
    """Rewrite package declaration to match directory structure."""
    package_pattern = re.compile(r'^package\s+([\w.]+)\s*;', re.MULTILINE)
    match = package_pattern.search(java_code)
    if match and match.group(1) != expected_package:
        java_code = package_pattern.sub(f"package {expected_package};", java_code)
    elif not match and expected_package:
        java_code = f"package {expected_package};\n\n{java_code}"
    return java_code
