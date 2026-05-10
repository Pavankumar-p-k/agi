#!/usr/bin/env python3
"""
Integrate extracted zip modules into the existing backend structure.
Does NOT duplicate - moves/copies smartly.
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"

def integrate_autonomous():
    """Move autonomous layer into backend/autonomy"""
    src_parent = ROOT / "jarvis_autonomous" / "jarvis_autonomous"
    if not src_parent.exists():
        print(f"[SKIP] {src_parent} not found")
        return
    
    dest = BACKEND / "autonomy"
    if dest.exists():
        print(f"[INFO] {dest} already exists, will merge")
        # Only copy missing directories
    else:
        dest.mkdir(parents=True, exist_ok=True)
    
    # Directories to copy
    dirs_to_copy = [
        "api", "cli", "core", "l1_brain", "l2_assistant", 
        "l3_executor", "l4_controller", "memory", "patches", 
        "config", "curriculum", "learning"
    ]
    
    for dirname in dirs_to_copy:
        src_dir = src_parent / dirname
        if src_dir.exists():
            dest_dir = dest / dirname
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            print(f"  Copying {dirname}/...")
            shutil.copytree(src_dir, dest_dir)
    
    # Files to copy
    files_to_copy = [
        "requirements_autonomous.txt",
        "setup.py",
        "ARCHITECTURE.md",
        "MIGRATION_GUIDE.md",
        "__init__.py"
    ]
    
    for filename in files_to_copy:
        src_file = src_parent / filename
        if src_file.exists():
            dest_file = dest / filename
            print(f"  Copying {filename}...")
            shutil.copy2(src_file, dest_file)
    
    print(f"✓ Autonomous layers integrated into {dest}")

def integrate_student_agi():
    """Move student AGI into backend/learning/student_agi"""
    src = ROOT / "jarvis_student_agi"
    if not src.exists():
        print(f"[SKIP] {src} not found")
        return
    
    dest = BACKEND / "learning" / "student_agi"
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    if dest.exists():
        shutil.rmtree(dest)
    
    print(f"  Copying student AGI...")
    shutil.copytree(src, dest)
    
    print(f"✓ Student AGI integrated into {dest}")

def integrate_flutter():
    """Merge Flutter apps into apps/jarvis_app/lib"""
    flutter_src = ROOT / "jarvis_final" / "lib"
    if not flutter_src.exists():
        print(f"[SKIP] {flutter_src} not found")
        return
    
    flutter_dest = ROOT / "apps" / "jarvis_app" / "lib"
    if not flutter_dest.exists():
        print(f"[SKIP] {flutter_dest} not found, cannot merge (app might not exist)")
        return
    
    # Only copy new directories/files
    print(f"  Merging Flutter lib...")
    for item in flutter_src.iterdir():
        dest_item = flutter_dest / item.name
        if dest_item.exists() and dest_item.is_dir():
            # Skip existing directories to avoid breaking the app
            print(f"    [SKIP] {item.name}/ (already exists)")
        else:
            print(f"    Copying {item.name}...")
            if item.is_dir():
                if dest_item.exists():
                    shutil.rmtree(dest_item)
                shutil.copytree(item, dest_item)
            else:
                shutil.copy2(item, dest_item)
    
    print(f"✓ Flutter app merged into {flutter_dest}")

def main():
    print("╔" + "═"*60 + "╗")
    print("║  JARVIS INTEGRATION: Extracted modules → Backend structure  ║")
    print("╚" + "═"*60 + "╝\n")
    
    print("[STEP 1] Autonomous layers...")
    integrate_autonomous()
    
    print("\n[STEP 2] Student AGI system...")
    integrate_student_agi()
    
    print("\n[STEP 3] Flutter app updates...")
    integrate_flutter()
    
    print("\n✓ Integration complete!")
    print("\nNext steps:")
    print("  1. python backend/autonomy/setup.py install")
    print("  2. pip install -r backend/requirements.txt")
    print("  3. python jarvis_main.py")

if __name__ == "__main__":
    main()
