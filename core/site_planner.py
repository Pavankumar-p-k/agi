"""core/site_planner.py
Takes structured intent from GoalInterpreter → detailed site plan.
Selects templates, maps pages, defines nav structure and design system.
"""
import re, json, logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("site_planner")

TEMPLATES_DIR = Path.home() / ".jarvis" / "templates" / "library"

TEMPLATE_MAP = {
    "book_store": ["ecommerce-store", "freshcart-tailwind-ecommerce-HTML-template", "landing"],
    "ecommerce": ["ecommerce-store", "freshcart-tailwind-ecommerce-HTML-template", "landing"],
    "coffee_shop": ["poco-html", "DinePro", "landing"],
    "restaurant": ["DinePro", "poco-html", "landing"],
    "tech_startup": ["landing", "poco-html", "airspace-bootstrap"],
    "portfolio": ["0xfolio", "dark-portfolio", "oftadeh-free-html5-portfolio", "minimal-portfolio-html-template"],
    "admin_dashboard": ["deskapp", "sneat-bootstrap-html-admin-template-free", "gentelella"],
    "blog": ["blogTemplate", "startbootstrap-clean-blog-jekyll", "landing"],
    "saas": ["landing", "poco-html", "aviato-bootstrap"],
    "landing": ["landing", "poco-html", "airspace-bootstrap"],
    "general": ["landing", "poco-html", "ecommerce-store"],
}

PAGE_GROUPS = {
    "primary": ["index", "home", "landing"],
    "info": ["about", "contact", "faq", "team", "story"],
    "content": ["blog", "portfolio", "gallery", "reviews", "testimonials"],
    "commerce": ["shop", "products", "catalog", "cart", "checkout", "pricing"],
    "auth": ["login", "signup", "register", "forgot"],
    "account": ["dashboard", "profile", "settings", "orders"],
    "legal": ["privacy", "terms", "cookies"],
}

NAV_POSITIONS = ["header", "footer", "sidebar", "mobile_menu"]

DESIGN_SYSTEM_DEFAULTS = {
    "modern_minimal": {
        "font": "Inter, sans-serif",
        "heading_font": "Inter, sans-serif",
        "primary_color": "#6366f1",
        "secondary_color": "#8b5cf6",
        "bg_color": "#ffffff",
        "text_color": "#1e293b",
        "border_radius": "8px",
        "spacing": "1rem",
        "max_width": "1200px",
    },
    "business": {
        "font": "Georgia, serif",
        "heading_font": "Merriweather, serif",
        "primary_color": "#1e40af",
        "secondary_color": "#3b82f6",
        "bg_color": "#f8fafc",
        "text_color": "#1e293b",
        "border_radius": "4px",
        "spacing": "1.5rem",
        "max_width": "1140px",
    },
    "ecommerce": {
        "font": "Inter, sans-serif",
        "heading_font": "Poppins, sans-serif",
        "primary_color": "#f97316",
        "secondary_color": "#fb923c",
        "bg_color": "#ffffff",
        "text_color": "#1e293b",
        "border_radius": "12px",
        "spacing": "1rem",
        "max_width": "1400px",
    },
    "creative": {
        "font": "Montserrat, sans-serif",
        "heading_font": "Playfair Display, serif",
        "primary_color": "#ec4899",
        "secondary_color": "#f472b6",
        "bg_color": "#0f172a",
        "text_color": "#f1f5f9",
        "border_radius": "16px",
        "spacing": "2rem",
        "max_width": "100%",
    },
    "saas": {
        "font": "Inter, sans-serif",
        "heading_font": "Inter, sans-serif",
        "primary_color": "#2563eb",
        "secondary_color": "#7c3aed",
        "bg_color": "#ffffff",
        "text_color": "#0f172a",
        "border_radius": "8px",
        "spacing": "1.5rem",
        "max_width": "1280px",
    },
    "blog": {
        "font": "Merriweather, serif",
        "heading_font": "Lora, serif",
        "primary_color": "#1a1a2e",
        "secondary_color": "#e94560",
        "bg_color": "#ffffff",
        "text_color": "#334155",
        "border_radius": "0px",
        "spacing": "1.5rem",
        "max_width": "800px",
    },
    "portfolio": {
        "font": "Inter, sans-serif",
        "heading_font": "Clash Display, sans-serif",
        "primary_color": "#000000",
        "secondary_color": "#facc15",
        "bg_color": "#ffffff",
        "text_color": "#1e293b",
        "border_radius": "0px",
        "spacing": "1rem",
        "max_width": "100%",
    },
}

FALLBACK_TEMPLATES = ["landing", "poco-html", "ecommerce-store"]


def select_template(goal: str, project_type: str = "website") -> Optional[str]:
    """Select best template path for goal. Returns path or None."""
    goal_lower = goal.lower().replace("_", " ")
    for kw, templates in TEMPLATE_MAP.items():
        search_kw = kw.lower().replace("_", " ")
        if kw in goal_lower or search_kw in goal_lower:
            for tpl_name in templates:
                tpl_path = TEMPLATES_DIR / tpl_name
                if tpl_path.exists():
                    return str(tpl_path)
    if project_type in ("dashboard", "admin"):
        for tpl in TEMPLATE_MAP["admin_dashboard"]:
            if (TEMPLATES_DIR / tpl).exists():
                return str(TEMPLATES_DIR / tpl)
    for tpl in FALLBACK_TEMPLATES:
        if (TEMPLATES_DIR / tpl).exists():
            return str(TEMPLATES_DIR / tpl)
    return None


def plan_site(interpreted: dict) -> dict:
    """Convert interpreted goal into a detailed site plan."""
    goal = interpreted.get("original_goal", "")
    project_type = interpreted.get("project_type", "website")
    pages = interpreted.get("pages", ["index", "about", "contact"])
    style = interpreted.get("style", "modern_minimal")
    tech_stack = interpreted.get("tech_stack", ["html", "css"])

    # 1. Select template
    template_path = select_template(goal, project_type)
    template_name = Path(template_path).name if template_path else None

    # 2. Classify pages into groups
    page_groups = {}
    for page in pages:
        for group, members in PAGE_GROUPS.items():
            if page in members:
                page_groups.setdefault(group, []).append(page)
                break
        else:
            page_groups.setdefault("other", []).append(page)

    # 3. Design system
    design_system = dict(DESIGN_SYSTEM_DEFAULTS.get(style, DESIGN_SYSTEM_DEFAULTS["modern_minimal"]))

    # 4. Nav structure
    nav_pages = [p for p in pages if p not in ("login", "signup", "cart", "checkout", "dashboard")]
    nav_structure = [
        {"label": p.replace("_", " ").replace("-", " ").title(), "href": f"{p}.html", "page": p}
        for p in nav_pages
    ]

    # 5. Framework decision
    framework = "static_html"
    if any(t in tech_stack for t in ("react", "nextjs")):
        framework = "react"
    elif any(t in tech_stack for t in ("vue", "nuxt")):
        framework = "vue"
    elif any(t in tech_stack for t in ("django", "flask", "fastapi")):
        framework = "backend_framework"

    # 6. Page metadata
    page_details = {}
    for page in pages:
        page_details[page] = {
            "filename": f"{page}.html",
            "title": page.replace("_", " ").replace("-", " ").title(),
            "group": next((g for g, ps in page_groups.items() if page in ps), "other"),
            "in_nav": page in nav_pages,
            "purpose": _page_purpose(page, goal),
        }

    # 7. Success criteria
    success_criteria = ["all_pages_exist", "no_broken_links", "nav_consistent", "html_valid", "css_applied"]
    if template_path:
        success_criteria.append("browser_loads")
    if project_type == "website":
        success_criteria.insert(0, "browser_loads")

    plan = {
        "template_path": template_path,
        "template_name": template_name,
        "framework": framework,
        "tech_stack": list(set(tech_stack + ["html", "css"])),
        "pages": list(pages),
        "page_details": page_details,
        "page_groups": page_groups,
        "nav_structure": nav_structure,
        "design_system": design_system,
        "style": style,
        "success_criteria": success_criteria,
        "constraints": interpreted.get("constraints", ["responsive"]),
        "tasks": _generate_tasks(project_type, pages, framework, template_path is not None),
    }

    logger.info(f"[SITEPLANNER] Planned {template_name or 'no-template'}: "
                f"{len(pages)} pages, {project_type}, {style}")
    return plan


def _page_purpose(page: str, goal: str) -> str:
    """Describe page purpose based on its name."""
    purposes = {
        "index": "Landing/home page with hero and overview",
        "home": "Landing/home page with hero and overview",
        "about": "Company/about information and mission",
        "contact": "Contact form and location details",
        "blog": "Articles and posts listing",
        "portfolio": "Work/project showcase gallery",
        "faq": "Frequently asked questions accordion",
        "pricing": "Pricing plans and feature comparison",
        "services": "Services offered with descriptions",
        "team": "Team member profiles and bios",
        "reviews": "Customer testimonials and reviews",
        "gallery": "Image gallery with lightbox",
        "cart": "Shopping cart with item listing and checkout button",
        "checkout": "Order checkout form with payment",
        "login": "User login form",
        "signup": "User registration/signup form",
        "dashboard": "User dashboard with account overview",
        "profile": "User profile edit page",
        "settings": "Account settings and preferences",
        "privacy": "Privacy policy document",
        "terms": "Terms of service document",
        "catalog": "Product/service catalog with grid layout",
        "shop": "Online shop with product grid and filters",
    }
    return purposes.get(page, f"{page.replace('_', ' ').title()} page")


def _generate_tasks(project_type: str, pages: list[str], framework: str, has_template: bool) -> list[dict]:
    """Generate build tasks based on the plan as a dependency DAG.
    Tasks with no cross-dependencies can be executed in parallel by control_loop."""
    tasks = []
    task_id = 0

    def add_task(ttype: str, desc: str, deps: list[str] = None, parallel_group: str = ""):
        nonlocal task_id
        task_id += 1
        tasks.append({
            "id": f"task_{task_id}",
            "type": ttype,
            "description": desc,
            "depends_on": deps or [],
            "parallel_group": parallel_group,
        })

    page_list = ", ".join(pages) if pages else "home, about, contact"

    if framework == "static_html" and has_template:
        add_task("scaffold", "Set up project structure")
        add_task("frontend", f"Apply template with pages: {page_list}", deps=["task_1"])
        if "contact" in pages:
            add_task("form", "Build contact form with validation", deps=[f"task_{task_id}"])
    elif framework == "static_html":
        add_task("scaffold", "Set up project structure")
        add_task("frontend", f"Build static site with pages: {page_list}", deps=["task_1"])
        add_task("styling", "Apply consistent styling across all pages", deps=[f"task_{task_id}"])
        if "contact" in pages:
            add_task("form", "Build contact form", deps=[f"task_{task_id}"])
        # Per-page frontend tasks for parallel generation (independent pages can build concurrently)
        for page in pages:
            if page != pages[0]:
                add_task("frontend", f"Build page: {page}", deps=["task_1"], parallel_group=page)
    elif framework == "react":
        add_task("scaffold", "Scaffold React project with Vite")
        add_task("frontend", f"Build React components for pages: {page_list}", deps=["task_1"])
        add_task("styling", f"Apply theming with {', '.join(pages)}", deps=["task_2"])
    elif framework == "backend_framework":
        add_task("scaffold", f"Scaffold {project_type} project")
        add_task("frontend", f"Build UI with pages: {page_list}", deps=["task_1"])
        add_task("backend", "Build API endpoints", deps=["task_1"])
        add_task("styling", "Apply styling", deps=["task_2"])

    tasks.sort(key=lambda t: {"scaffold": 0, "frontend": 1, "backend": 2, "database": 3, "auth": 4, "form": 5, "styling": 6, "test": 7, "deploy": 8}.get(t["type"], 99))
    return tasks
