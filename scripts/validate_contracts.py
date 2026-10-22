"""Validate schemas, examples and the committed local API contract."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "projects/traffic-light"), str(ROOT / 'platform/registry'),
               str(ROOT / 'platform/ingestion')]

from app.main import app  # noqa: E402
from iot_shared.canonical import SCHEMA, VALIDATOR  # noqa: E402
from registry_service.api import app as registry_app  # noqa: E402
from ingestion_service.api import app as ingestion_app  # noqa: E402
from ingestion_service.query_api import app as data_app  # noqa: E402


def main():
    import yaml

    VALIDATOR.check_schema(SCHEMA)
    examples = list((ROOT / "contracts/examples").glob("*.json"))
    assert examples, "Missing canonical examples"
    for path in examples:
        VALIDATOR.validate(json.loads(path.read_text(encoding="utf-8")))
    expected = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    assert expected == app.openapi(), "OpenAPI differs from implementation: regenerate and review the contract"
    registry_expected = yaml.safe_load((ROOT / 'contracts/registry-openapi.yaml').read_text(encoding='utf-8'))
    assert registry_expected == registry_app.openapi(), 'Registry OpenAPI differs from implementation'
    for name, application in [('ingestion', ingestion_app), ('data', data_app)]:
        expected = yaml.safe_load((ROOT / f'contracts/{name}-openapi.yaml').read_text(encoding='utf-8'))
        assert expected == application.openapi(), f'{name} OpenAPI differs from implementation'
    print(f"Canonical schema, {len(examples)} examples and four OpenAPI contracts validated")


if __name__ == "__main__":
    main()
