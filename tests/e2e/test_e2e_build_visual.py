"""Playwright-based visual verification tests for JARVIS builds.
Tests that generated HTML pages load without errors and have expected structure.
"""
import pytest
import asyncio
from pathlib import Path


pytestmark = pytest.mark.asyncio


class TestBuildVisual:
    """Tests that generated build output is visually valid using Playwright."""

    @pytest.mark.e2e
    @pytest.mark.skipif("not pytestconfig.getoption('--run-e2e', default=False)")
    async def test_build_output_loads(self, tmp_path):
        """Generate a minimal page and verify Playwright loads it without errors."""
        playwright = pytest.importorskip("playwright")
        from playwright.async_api import async_playwright

        html = """<!DOCTYPE html><html><body><h1>Hello</h1></body></html>"""
        html_path = tmp_path / "index.html"
        html_path.write_text(html, encoding="utf-8")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            errors = []

            def _on_error(msg):
                errors.append(str(msg))

            page.on("pageerror", _on_error)
            await page.goto(f"file://{html_path.resolve()}", timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_timeout(500)

            h1 = await page.query_selector("h1")
            text = await h1.inner_text() if h1 else ""
            await browser.close()

        assert not errors, f"Page had JS errors: {errors}"
        assert text == "Hello"

    @pytest.mark.e2e
    @pytest.mark.skipif("not pytestconfig.getoption('--run-e2e', default=False)")
    async def test_build_visual_quality(self, tmp_path):
        """Run the visual quality checker on a generated page."""
        from core.real_validator import RealValidator, ValidationResult
        from core.project_state import ProjectState

        html = """<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><h1>Test Page</h1><p>Some content here.</p></body></html>"""
        html_path = tmp_path / "index.html"
        html_path.write_text(html, encoding="utf-8")

        state = ProjectState(project_name="test_viz", goal="test visual quality")
        state.interpreted_goal = {"original_goal": "test page", "brand_name": "Test", "business_type": "general"}
        state.save()

        validator = RealValidator(str(tmp_path))
        result = await validator.check_visual_quality(state, tmp_path)

        assert isinstance(result, ValidationResult)
        assert result.check == "visual_quality"
