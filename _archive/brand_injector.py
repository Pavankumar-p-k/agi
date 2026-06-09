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

"""core/brand_injector.py
AST-based brand name injection using BeautifulSoup.
Replaces visible text nodes only — never touches attributes or SVG content.
"""
import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

TEMPLATE_BRANDS = [
    "Ecommerce Store", "E-Commerce Store", "Ecommerce",
    "DinePro", "Poco", "Landing", "Startup", "Business", "Company",
    "Portfolio", "DeskApp", "Deskapp", "FreshCart", "freshcart",
    "Gentelella", "StartBootstrap", "Startbootstrap", "Aviato",
    "Rappo", "Vex", "Constra", "PurpleAdmin", "StarAdmin",
    "Sneat", "sneat", "Website", "website",
    "Book Store", "Coffee Shop", "Restaurant", "Blog",
    "Admin", "Dashboard", "Agency", "Digital Agency",
]


def inject_brand(html: str, brand_name: str, business_type: str = "") -> str:
    """Inject brand name into HTML using AST — never touches attributes or SVG."""
    soup = BeautifulSoup(html, 'lxml')

    # Replace <title> content
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip()
        new_title = _replace_brand_in_text(title_text, brand_name, business_type)
        soup.title.string = new_title

    # Replace meta description
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        old_desc = meta_desc['content']
        meta_desc['content'] = _replace_brand_in_text(old_desc, brand_name, business_type)

    # Replace visible text nodes ONLY
    for element in soup.find_all(string=True):
        parent = element.parent
        # Skip script, style, SVG elements and their content
        if _is_protected_element(parent):
            continue
        # Skip attribute values — never touch src, href, viewBox, data-*, etc.
        if isinstance(element, str) and element.strip():
            new_text = _replace_brand_in_text(element, brand_name, business_type)
            if new_text != element:
                element.replace_with(new_text)

    return str(soup)


def _is_protected_element(element) -> bool:
    """Check if an element should never have its text content replaced."""
    protected_tags = {'script', 'style', 'svg', 'path', 'circle', 'rect',
                      'line', 'polyline', 'polygon', 'text', 'tspan',
                      'use', 'g', 'defs', 'symbol', 'marker',
                      'clipPath', 'mask', 'pattern', 'linearGradient',
                      'radialGradient', 'stop', 'filter', 'feGaussianBlur',
                      'feOffset', 'feMerge', 'feMergeNode', 'feFlood',
                      'feColorMatrix', 'feComposite', 'feBlend'}
    current = element
    # Walk up the tree to check if we're inside any protected element
    while current is not None:
        try:
            name = getattr(current, 'name', None)
            if name and name.lower() in protected_tags:
                return True
        except Exception as e:
            logger.exception("[BRAND] check error: %s", e)
        current = getattr(current, 'parent', None)
    return False


def _replace_brand_in_text(text: str, brand_name: str, business_type: str = "") -> str:
    """Replace any known template brand name in visible text using word boundaries."""
    new_text = text
    for old_brand in TEMPLATE_BRANDS:
        pattern = r'\b' + re.escape(old_brand) + r'\b'
        new_text = re.sub(pattern, brand_name, new_text, flags=re.IGNORECASE)
    # Also replace generic placeholders
    new_text = re.sub(r'\bYour\s+Company\s+Name\b', brand_name, new_text, flags=re.IGNORECASE)
    new_text = re.sub(r'\bCompany\s+Name\b', brand_name, new_text, flags=re.IGNORECASE)
    return new_text
