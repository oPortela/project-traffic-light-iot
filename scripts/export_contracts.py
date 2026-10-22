"""Export local OpenAPI contracts; review the diff before committing."""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'platform/registry'), str(ROOT / 'platform/ingestion')]
from registry_service.api import app as registry  # noqa: E402
from ingestion_service.api import app as ingestion  # noqa: E402
from ingestion_service.query_api import app as data  # noqa: E402

for name, app in [('registry', registry), ('ingestion', ingestion), ('data', data)]:
    (ROOT / f'contracts/{name}-openapi.yaml').write_text(
        yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False), encoding='utf-8')

version = ROOT / 'contracts/v1'
version.mkdir(exist_ok=True)
for name in ('openapi.yaml', 'registry-openapi.yaml', 'ingestion-openapi.yaml', 'data-openapi.yaml', 'asyncapi.yaml'):
    (version / name).write_bytes((ROOT / 'contracts' / name).read_bytes())
