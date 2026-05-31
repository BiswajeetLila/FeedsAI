"""
app/templates_config.py
Single shared Jinja2Templates instance used across all routers.
"""
from fastapi.templating import Jinja2Templates

from app.paths import resource_path

templates = Jinja2Templates(directory=str(resource_path("app", "templates")))
