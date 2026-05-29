"""
app/templates_config.py
Single shared Jinja2Templates instance used across all routers.
"""
from pathlib import Path

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
