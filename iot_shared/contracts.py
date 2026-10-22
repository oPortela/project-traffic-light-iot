"""Read-only, versioned contracts served without credentials."""
from pathlib import Path

from fastapi.staticfiles import StaticFiles


def publish_contracts(app):
    app.mount('/contratos', StaticFiles(directory=Path(__file__).resolve().parent.parent / 'contracts'),
              name='contratos')
