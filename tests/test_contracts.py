from copy import deepcopy

import pytest
from jsonschema import ValidationError

from iot_shared.canonical import envelope, topic, validate


@pytest.fixture
def message():
    return envelope({"inquilino": "semob", "site": "centro", "dominio": "mobilidade",
                     "dispositivo": "semaforo-travessia-01"}, "telemetria",
                    {"pedestres_na_area": {"valor": 2, "unidade": "1"}})


def test_valid_message_and_topic(message):
    assert validate(message) == message
    assert topic(message) == "semob/centro/mobilidade/semaforo-travessia-01/telemetria"


@pytest.mark.parametrize("key,value", [
    ("timestamp", "2026-01-01T00:00:00"),
    ("timestamp", "2026-01-01T00:00:00-03:00"),
    ("timestamp", "2026-99-99T00:00:00Z"),
    ("id_mensagem", "not-a-uuid"),
    ("inquilino", "other/#"),
    ("versao", "2.0"),
    ("dados", {"imagem": "base64"}),
    ("dados", {"temperatura": {"valor": "vinte", "unidade": "Cel"}}),
])
def test_invalid_messages(message, key, value):
    invalid = deepcopy(message)
    invalid[key] = value
    with pytest.raises(ValidationError):
        validate(invalid)


def test_required_field(message):
    del message["id_mensagem"]
    with pytest.raises(ValidationError):
        validate(message)


@pytest.mark.parametrize('number', [float('nan'), float('inf'), float('-inf')])
def test_non_json_numbers_are_rejected(message, number):
    message['dados']['pedestres_na_area']['valor'] = number
    with pytest.raises(ValueError):
        validate(message)
