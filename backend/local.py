"""Single-origin local/Quick Tunnel entry point; build the frontend first."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from backend.app import app


dist = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'
if not (dist / 'index.html').is_file():
    raise RuntimeError('Build frontend first: npm.cmd --prefix frontend run build')
app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
