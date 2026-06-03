"""core/image_pipeline.py
Fetches real images for website builds. Pexels API primary, gradient fallback.
"""
import os
import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("image_pipeline")

CACHE_DIR = Path.home() / ".jarvis" / ".image_cache"

# Context → search query mapping per business type
CONTEXT_QUERIES = {
    "hero": {
        "restaurant": "restaurant interior dining",
        "coffee_shop": "coffee shop interior",
        "bakery": "bakery bread pastry",
        "hotel": "hotel lobby luxury",
        "portfolio": "creative workspace",
        "blog": "workspace desk laptop",
        "ecommerce": "product display",
        "saas": "modern office technology",
        "tech_startup": "startup team office",
        "fitness": "gym workout equipment",
        "spa": "spa massage relaxing",
        "salon": "hair salon interior",
        "real_estate": "modern house exterior",
        "law_firm": "law office professional",
        "dental_clinic": "dental clinic modern",
        "book_store": "bookstore interior books",
        "music_store": "music store instruments",
        "general": "modern business office",
    },
    "about": {
        "restaurant": "chef cooking kitchen",
        "coffee_shop": "barista making coffee",
        "bakery": "baker kneading dough",
        "hotel": "hotel staff service",
        "portfolio": "designer working studio",
        "blog": "writer typing laptop",
        "ecommerce": "warehouse packaging",
        "saas": "developers team meeting",
        "tech_startup": "founders brainstorming",
        "general": "team collaboration office",
    },
    "team": {
        "__default__": "diverse professionals team smiling",
    },
    "featured": {
        "__default__": "product showcase display",
    },
    "contact": {
        "__default__": "modern building exterior",
    },
}

GRADIENT_COLORS = {
    "restaurant": ("#B91C1C", "#DC2626"),
    "coffee_shop": ("#6F4E37", "#A0522D"),
    "bakery": ("#D4A574", "#8B4513"),
    "hotel": ("#1E3A5F", "#2563EB"),
    "portfolio": ("#7C3AED", "#8B5CF6"),
    "blog": ("#1D4ED8", "#2563EB"),
    "ecommerce": ("#DC2626", "#EF4444"),
    "saas": ("#059669", "#10B981"),
    "tech_startup": ("#1E3A5F", "#2563EB"),
    "fitness": ("#059669", "#10B981"),
    "general": ("#2563EB", "#3B82F6"),
}


def _get_image_cache_path(url: str) -> Path:
    # Use SHA256 instead of MD5 for better collision resistance
    h = hashlib.sha256(url.encode()).hexdigest()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{h}.jpg"


async def fetch_image(context: str, business_type: str = "general",
                      width: int = 1200, height: int = 800) -> Optional[str]:
    """Fetch an image matching context+business_type. Returns local path or None."""
    _ = width  # width parameter reserved for future resizing; mark as used to satisfy linters
    query = _resolve_query(context, business_type)
    pexels_key = os.getenv("PEXELS_API_KEY", "").strip()

    # Try Pexels if key is configured
    if pexels_key:
        try:
            import httpx
            url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=landscape"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url, headers={"Authorization": pexels_key}
                )
            if resp.status_code == 200:
                data = resp.json()
                photos = data.get("photos", [])
                if photos:
                    photo_url = photos[0]["src"]["large"]
                    cache_path = _get_image_cache_path(photo_url)
                    if not cache_path.exists():
                        async with httpx.AsyncClient(timeout=15) as img_client:
                            img_resp = await img_client.get(photo_url)
                        if img_resp.status_code == 200:
                            cache_path.write_bytes(img_resp.content)
                    return str(cache_path) if cache_path.exists() else None
        except Exception as e:
            logger.debug(f"[IMAGES] Pexels fetch failed: {e}")

    return None


def gradient_placeholder_html(business_type: str = "general",
                               width: int = 800, height: int = 400) -> str:
    """Generate an inline CSS gradient placeholder div (no broken img tag)."""
    _ = width  # width is currently unused but kept for API compatibility
    colors = GRADIENT_COLORS.get(business_type, GRADIENT_COLORS["general"])
    return (
        f'<div style="background:linear-gradient(135deg,{colors[0]},{colors[1]});'
        f'width:100%;min-height:{height}px;display:flex;align-items:center;'
        f'justify-content:center;color:#fff;font-size:2rem;border-radius:12px;">'
        f'<i class="fas fa-image" style="opacity:0.6"></i></div>'
    )


def _resolve_query(context: str, business_type: str) -> str:
    """Map (context, business_type) to a search query string."""
    context_map = CONTEXT_QUERIES.get(context, {})
    if business_type in context_map:
        return context_map[business_type]
    if "__default__" in context_map:
        return context_map["__default__"]
    return f"{business_type.replace('_', ' ')} {context}"
