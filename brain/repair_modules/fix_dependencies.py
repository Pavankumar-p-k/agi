"""brain/repair_modules/fix_dependencies.py
Deterministic Gradle dependency repair.
Adds missing dependencies based on missing class errors.
"""
import re

DEPENDENCY_MAP: dict[str, str] = {
    "RecyclerView": "implementation 'androidx.recyclerview:recyclerview:1.3.2'",
    "LiveData": "implementation 'androidx.lifecycle:lifecycle-livedata-ktx:2.7.0'",
    "ViewModel": "implementation 'androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0'",
    "Room": "implementation 'androidx.room:room-runtime:2.6.1'",
    "Database": "implementation 'androidx.room:room-runtime:2.6.1'",
    "Dao": "implementation 'androidx.room:room-runtime:2.6.1'",
    "Entity": "implementation 'androidx.room:room-runtime:2.6.1'",
    "Navigation": "implementation 'androidx.navigation:navigation-fragment-ktx:2.7.7'",
    "NavController": "implementation 'androidx.navigation:navigation-fragment-ktx:2.7.7'",
    "NavHostFragment": "implementation 'androidx.navigation:navigation-fragment-ktx:2.7.7'",
    "Gson": "implementation 'com.google.code.gson:gson:2.10.1'",
    "GsonBuilder": "implementation 'com.google.code.gson:gson:2.10.1'",
    "MaterialButton": "implementation 'com.google.android.material:material:1.11.0'",
    "MaterialCardView": "implementation 'com.google.android.material:material:1.11.0'",
    "BottomNavigationView": "implementation 'com.google.android.material:material:1.11.0'",
    "ViewPager2": "implementation 'androidx.viewpager2:viewpager2:1.0.0'",
    "FragmentStateAdapter": "implementation 'androidx.viewpager2:viewpager2:1.0.0'",
}


def fix_dependencies(build_gradle_path: str, errors: list[dict]) -> bool:
    """Add missing Gradle dependencies based on error analysis."""
    try:
        with open(build_gradle_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return False

    needed = set()
    for error in errors:
        msg = error.get("message", "")
        symbol = error.get("symbol", "")
        for cls, dep in DEPENDENCY_MAP.items():
            if cls in msg or cls in symbol:
                needed.add(dep)

    added = False
    if needed:
        deps_section = "\n".join(sorted(needed))
        content = content.rstrip()
        if "dependencies {" in content:
            existing_deps = set(re.findall(r"implementation\s+'[\w.:-]+'", content))
            new_deps = [d for d in needed if d not in existing_deps]
            if new_deps:
                insert = "\n    " + "\n    ".join(new_deps)
                content = content.replace("dependencies {", f"dependencies {{{insert}")
                added = True
        else:
            content += f"\n\ndependencies {{\n{needed}\n}}\n"
            added = True

    if added:
        with open(build_gradle_path, "w", encoding="utf-8") as f:
            f.write(content)
    return added
