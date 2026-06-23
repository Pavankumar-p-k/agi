"""core/routes/features.py — Feature Registry REST API."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, HTTPException, Query
    _FASTAPI = True
except ImportError:
    _FASTAPI = False

if _FASTAPI:
    router = APIRouter(tags=["features"])

    @router.get("/api/features")
    async def list_features(category: Optional[str] = Query(None)):
        from core.feature_registry import get_all_features, get_features_by_category
        if category:
            return {"features": get_features_by_category(category), "total": 0}
        features = get_all_features()
        return {
            "features": features,
            "total": len(features),
        }

    @router.get("/api/features/categories")
    async def get_feature_categories():
        from core.feature_registry import get_all_features
        features = get_all_features()
        categories: dict[str, list[dict]] = {}
        for f in features:
            cat = f["category"]
            categories.setdefault(cat, []).append(f)
        return {
            "categories": [
                {"id": cat, "label": cat.replace("_", " ").title(), "count": len(items)}
                for cat, items in sorted(categories.items())
            ],
        }

    @router.get("/api/features/{slug}")
    async def get_feature_detail(slug: str):
        from core.feature_registry import FEATURES, get_status, is_enabled, Feature
        feature: Feature | None = FEATURES.get(slug)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature '{slug}' not found")
        report = {
            "name": feature.name,
            "slug": slug,
            "status": get_status(slug).value,
            "enabled": is_enabled(slug),
            "category": feature.category,
            "description": feature.description,
            "config_key": feature.config_key,
            "dependencies": feature.dependencies,
            "docs_path": feature.docs_path,
            "tests_path": feature.tests_path,
            "health_check_fn": feature.health_check_fn,
            "enabled_by_default": feature.enabled_by_default,
        }

        if feature.health_check_fn:
            try:
                mod_path, _, fn_name = feature.health_check_fn.rpartition(":")
                if mod_path and fn_name:
                    import importlib
                    mod = importlib.import_module(mod_path)
                    fn = getattr(mod, fn_name)
                    import asyncio
                    result = await asyncio.wait_for(fn() if asyncio.iscoroutinefunction(fn) else fn(), timeout=5.0)
                    report["health"] = {
                        "ok": True,
                        "data": result if isinstance(result, dict) else str(result),
                    }
            except Exception as e:
                report["health"] = {"ok": False, "error": str(e)}

        return report

    @router.post("/api/features/{slug}/toggle")
    async def toggle_feature(slug: str, body: Optional[dict] = None):
        enabled = True
        if body and "enabled" in body:
            enabled = bool(body["enabled"])
        from core.feature_registry import FEATURES, set_status, FeatureStatus
        if slug not in FEATURES:
            raise HTTPException(status_code=404, detail=f"Feature '{slug}' not found")
        from core.config_registry import config
        config.set(f"feature.{slug}.enabled", enabled)
        new_status = FeatureStatus.STABLE if enabled else FeatureStatus.BROKEN
        set_status(slug, new_status)
        return {
            "slug": slug,
            "enabled": enabled,
            "message": f"Feature '{slug}' {'enabled' if enabled else 'disabled'}",
        }

    @router.get("/api/features/report")
    async def get_feature_report():
        from core.feature_registry import get_feature_report
        return get_feature_report()
else:
    class router:
        pass
