"""Validate schemas, examples and the committed local API contract."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "projects/traffic-light")]

from app.main import app  # noqa: E402
from iot_shared.canonical import SCHEMA, VALIDATOR  # noqa: E402


def main():
    import yaml

    VALIDATOR.check_schema(SCHEMA)
    examples = list((ROOT / "contracts/examples").glob("*.json"))
    assert examples, "Missing canonical examples"
    for path in examples:
        VALIDATOR.validate(json.loads(path.read_text(encoding="utf-8")))
    expected = yaml.safe_load((ROOT / "contracts/openapi.yaml").read_text(encoding="utf-8"))
    assert expected == app.openapi(), "OpenAPI differs from implementation: regenerate and review the contract"
    print(f"Canonical schema, {len(examples)} examples and OpenAPI validated")


if __name__ == "__main__":
    main()
