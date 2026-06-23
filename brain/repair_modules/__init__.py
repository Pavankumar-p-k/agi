"""brain/repair_modules/
Deterministic Android build repair modules.
Each module handles one category of compilation error.
"""
from brain.repair_modules import fix_imports as _fix_imports_mod
from brain.repair_modules import fix_class_names as _fix_class_names_mod
from brain.repair_modules import fix_manifest as _fix_manifest_mod
from brain.repair_modules import fix_layouts as _fix_layouts_mod
from brain.repair_modules import fix_resources as _fix_resources_mod
from brain.repair_modules import fix_gradle as _fix_gradle_mod
from brain.repair_modules import fix_dependencies as _fix_dependencies_mod
from brain.repair_modules import fix_file_ops as _fix_file_ops_mod
from brain.repair_modules import fix_syntax as _fix_syntax_mod

# Export functions
fix_imports = _fix_imports_mod.fix_imports
fix_package_names = _fix_imports_mod.fix_package_names
fix_class_names = _fix_class_names_mod.fix_class_names
fix_manifest = _fix_manifest_mod.fix_manifest
fix_layouts = _fix_layouts_mod.fix_layouts
fix_resources = _fix_resources_mod.fix_resources
fix_gradle = _fix_gradle_mod.fix_gradle
fix_dependencies = _fix_dependencies_mod.fix_dependencies
fix_file_ops = _fix_file_ops_mod
fix_syntax = _fix_syntax_mod

__all__ = [
    "fix_imports", "fix_class_names", "fix_manifest",
    "fix_layouts", "fix_resources", "fix_gradle",
    "fix_dependencies", "fix_package_names",
    "fix_file_ops", "fix_syntax",
]

REPAIR_MODULES = {
    "fix_imports": fix_imports,
    "fix_class_names": fix_class_names,
    "fix_manifest": fix_manifest,
    "fix_layouts": fix_layouts,
    "fix_resources": fix_resources,
    "fix_gradle": fix_gradle,
    "fix_dependencies": fix_dependencies,
    "fix_package_names": fix_package_names,
    "fix_file_ops": fix_file_ops,
    "fix_syntax": fix_syntax,
}
