# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
tools/scene_generator.py
Phase 10.3 — 3D Scene Generator

Two modes based on target:
  1. Three.js (web) — LLM generates self-contained HTML+Three.js scene
     → returns HTML string, renderable in browser/dashboard artifact
  2. Blender (offline) — LLM generates Blender Python (bpy) script
     → executes headless Blender, returns path to rendered PNG

Mode is auto-selected based on output_format parameter:
  "web"    → Three.js HTML (always available, no extra deps)
  "blender"→ Blender bpy script (needs Blender installed)
  "auto"   → "web" if Blender not found, else "blender"

Self-correction loop:
  - Blender mode: parse stderr → feed error to LLM → retry (max 3x)
  - Three.js mode: validate output contains scene setup → retry if missing

Cross-checks against your stack:
  - Uses brain.reason() with "coder" system prompt (Phase 1 prompts.py ✓)
  - Returns artifact_code for dashboard rendering (Phase 7 MultiFormatResponse ✓)
  - Error recovery via same retry pattern as TestDrivenGenerator (Phase 5 ✓)

Dependencies:
  Three.js — no install needed (CDN import in generated HTML)
  Blender   — system install, optional: https://www.blender.org/download/
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from brain.UnifiedBrain import UnifiedBrain

logger = logging.getLogger(__name__)

BLENDER_TIMEOUT = 120   # seconds
MAX_RETRIES     = 3


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SceneResult:
    success:       bool
    output_format: str            # "threejs" | "blender"
    artifact_code: Optional[str]  # HTML string (Three.js) or None (Blender)
    render_path:   Optional[str]  # PNG path (Blender) or None (Three.js)
    script:        Optional[str]  # the generated script/HTML for inspection
    attempts:      int = 1
    error:         Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Three.js generator
# ─────────────────────────────────────────────────────────────────────────────

class ThreeJSGenerator:
    """
    Generates a self-contained HTML file with embedded Three.js scene.
    Loaded from CDN — no npm, no bundler, works in any browser.
    """

    SYSTEM_PROMPT = (
        "You are a Three.js expert. Generate a complete, self-contained HTML file "
        "with an embedded Three.js r128 scene. Rules:\n"
        "1. Import Three.js from: https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js\n"
        "2. Include OrbitControls if rotation needed (same CDN path)\n"
        "3. Scene must auto-resize with window\n"
        "4. Add ambient + directional lighting\n"
        "5. Output ONLY the complete HTML — no explanation, no markdown fences\n"
        "6. Start output with <!DOCTYPE html>"
    )

    async def generate(self, description: str, brain: "UnifiedBrain") -> SceneResult:
        prompt = (
            f"Create a Three.js 3D scene for: {description}\n\n"
            f"Requirements:\n"
            f"- Render the described scene with appropriate geometry\n"
            f"- Use realistic materials and colors\n"
            f"- Add smooth animation (requestAnimationFrame)\n"
            f"- Camera positioned to show the full scene\n"
            f"- Background color: #1a1a2e (dark blue)"
        )

        for attempt in range(1, MAX_RETRIES + 1):
            result = await brain.reason(
                f"{self.SYSTEM_PROMPT}\n\n{prompt}"
            )
            html = result.answer.strip()

            # Strip accidental markdown fences
            html = re.sub(r"^```html?\s*", "", html, flags=re.IGNORECASE)
            html = re.sub(r"\s*```$", "", html)

            # Validate: must be a real HTML file with Three.js
            if self._is_valid(html):
                return SceneResult(
                    success       = True,
                    output_format = "threejs",
                    artifact_code = html,
                    render_path   = None,
                    script        = html,
                    attempts      = attempt,
                )

            # Inject failure context and retry
            prompt = (
                f"{prompt}\n\n"
                f"Previous attempt {attempt} was invalid. "
                f"The HTML must start with <!DOCTYPE html> and import three.js. "
                f"Output ONLY raw HTML, no markdown, no explanation."
            )
            logger.debug("ThreeJS generation attempt %d failed validation", attempt)

        return SceneResult(
            success=False, output_format="threejs",
            artifact_code=None, render_path=None, script=None,
            attempts=MAX_RETRIES,
            error="Three.js generation failed validation after max retries"
        )

    def _is_valid(self, html: str) -> bool:
        return (
            "<!DOCTYPE html>" in html.lower() or "<html" in html.lower()
        ) and "three" in html.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Blender generator
# ─────────────────────────────────────────────────────────────────────────────

class BlenderGenerator:
    """
    Generates a Blender Python (bpy) script, executes headless Blender,
    returns path to rendered PNG.

    Self-correction: stderr → LLM fix → retry (max 3x).
    """

    SYSTEM_PROMPT = (
        "You are a Blender Python (bpy) expert. Generate a complete, runnable bpy script. "
        "Rules:\n"
        "1. Always start with: import bpy\n"
        "2. Clear the scene first: bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()\n"
        "3. Set render output: bpy.context.scene.render.filepath = '/tmp/jarvis_render.png'\n"
        "4. Set resolution: bpy.context.scene.render.resolution_x = 1920; ...y = 1080\n"
        "5. Use CYCLES or EEVEE render engine\n"
        "6. Add camera + lighting\n"
        "7. End with: bpy.ops.render.render(write_still=True)\n"
        "8. Output ONLY the Python script — no explanation, no markdown"
    )

    async def generate(self,
                        description: str,
                        brain: "UnifiedBrain",
                        output_path: str = "/tmp/jarvis_render.png") -> SceneResult:

        blender_bin = shutil.which("blender")
        if not blender_bin:
            return SceneResult(
                success=False, output_format="blender",
                artifact_code=None, render_path=None, script=None,
                error="Blender not found in PATH. Install from blender.org"
            )

        prompt = (
            f"Write a Blender bpy script to create a 3D scene of: {description}\n\n"
            f"Make it visually interesting with proper materials, lighting, and camera angle. "
            f"Render output path: {output_path}"
        )

        last_error = ""
        for attempt in range(1, MAX_RETRIES + 1):
            # Build prompt with previous error context
            full_prompt = prompt
            if last_error:
                full_prompt += (
                    f"\n\nPrevious attempt {attempt-1} produced this error:\n"
                    f"{last_error[:800]}\n\n"
                    f"Fix the error and rewrite the complete script."
                )

            result = await brain.reason(
                f"{self.SYSTEM_PROMPT}\n\n{full_prompt}"
            )
            script = result.answer.strip()
            script = re.sub(r"^```python?\s*", "", script, flags=re.IGNORECASE)
            script = re.sub(r"\s*```$", "", script)

            if not script.startswith("import bpy"):
                last_error = "Script must start with 'import bpy'"
                continue

            # Execute headless Blender
            exec_result = await self._execute(blender_bin, script)

            if exec_result["success"]:
                return SceneResult(
                    success       = True,
                    output_format = "blender",
                    artifact_code = None,
                    render_path   = output_path,
                    script        = script,
                    attempts      = attempt,
                )

            last_error = exec_result["stderr"][:600]
            logger.debug("Blender attempt %d failed: %s", attempt, last_error[:100])

        return SceneResult(
            success=False, output_format="blender",
            artifact_code=None, render_path=None, script=None,
            attempts=MAX_RETRIES,
            error=f"Blender render failed after {MAX_RETRIES} attempts. Last error: {last_error[:200]}"
        )

    async def _execute(self, blender_bin: str, script: str) -> dict:
        """Write script to temp file, run headless Blender, return result."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            script_path = f.name

        try:
            proc = await asyncio.create_subprocess_exec(
                blender_bin,
                "--background",
                "--python", script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=BLENDER_TIMEOUT
                )
            except asyncio.TimeoutError:
                proc.kill()
                return {"success": False, "stderr": f"Blender timed out after {BLENDER_TIMEOUT}s"}

            success = proc.returncode == 0
            return {
                "success": success,
                "stdout":  stdout.decode(errors="replace"),
                "stderr":  stderr.decode(errors="replace"),
            }
        finally:
            Path(script_path).unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# SceneGenerator — unified entry point
# ─────────────────────────────────────────────────────────────────────────────

class SceneGenerator:
    """
    Auto-selects Three.js or Blender based on availability and format param.

    Usage:
        result = await scene_generator.generate(
            description   = "a futuristic city at night with neon lights",
            brain         = unified_brain,
            output_format = "auto"   # "web" | "blender" | "auto"
        )
        if result.success:
            if result.artifact_code:   # Three.js — show in dashboard
                return MultiFormatResponse(artifact_code=result.artifact_code,
                                            artifact_type="html")
            if result.render_path:     # Blender — return image path
                return result.render_path
    """

    def __init__(self):
        self._threejs = ThreeJSGenerator()
        self._blender = BlenderGenerator()

    async def generate(self,
                        description:   str,
                        brain:         "UnifiedBrain",
                        output_format: str = "auto") -> SceneResult:
        fmt = self._resolve_format(output_format)
        logger.info("SceneGenerator: generating '%s' as %s", description[:50], fmt)

        if fmt == "threejs":
            return await self._threejs.generate(description, brain)
        else:
            result = await self._blender.generate(description, brain)
            if not result.success:
                # Fallback to Three.js if Blender fails
                logger.info("SceneGenerator: Blender failed, falling back to Three.js")
                return await self._threejs.generate(description, brain)
            return result

    def _resolve_format(self, fmt: str) -> str:
        if fmt == "web":
            return "threejs"
        if fmt == "blender":
            return "blender"
        # auto: prefer Three.js (always available), Blender if installed
        return "blender" if shutil.which("blender") else "threejs"


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────
scene_generator = SceneGenerator()
