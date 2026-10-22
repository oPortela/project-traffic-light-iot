"""Canonical v1 messages. Wall-clock conversion belongs at the protocol boundary."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft7Validator, FormatChecker

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
SCHEMA = json.loads((CONTRACTS / "schemas/canonical-1.0.json").read_text(encoding="utf-8"))
VALIDATOR = Draft7Validator(SCHEMA, format_checker=FormatChecker())


def validate(message):
    # Python's JSON decoder accepts NaN/Infinity; canonical JSON does not.
    json.dumps(message, allow_nan=False)
    VALIDATOR.validate(message)
    return message


def timestamp(monotonic, *, reference_monotonic, reference_utc):
    return (reference_utc + timedelta(seconds=monotonic - reference_monotonic)).astimezone(
        timezone.utc
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def envelope(identity, kind, data, *, occurred_at=None):
    return validate({
        "versao": "1.0",
        "id_mensagem": str(uuid4()),
        "timestamp": occurred_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **identity,
        "tipo": kind,
        "dados": data,
    })


def topic(message):
    return "/".join(message[key] for key in ("inquilino", "site", "dominio", "dispositivo", "tipo"))
