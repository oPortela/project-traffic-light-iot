"""Registry contracts; domain definitions are configuration, never code branches."""
from typing import Annotated, Literal
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')]


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Named(Model):
    id: Identifier
    nome: str = Field(min_length=1, max_length=160)


class Measurement(Model):
    unidade: str = Field(min_length=1, max_length=32, pattern=r'^\S+$')
    minimo: float
    maximo: float

    @model_validator(mode='after')
    def valid_range(self):
        if self.minimo > self.maximo:
            raise ValueError('minimo deve ser menor ou igual a maximo')
        return self


class DataField(Model):
    tipo: Literal['numero', 'booleano', 'enum', 'vetor']
    valores: list[str] = Field(default_factory=list, max_length=100)
    tamanho: int = Field(default=4, ge=1, le=16)
    minimo: float | None = None
    maximo: float | None = None
    retangulo: bool = False

    @model_validator(mode='after')
    def bounded_enum(self):
        if self.minimo is not None and self.maximo is not None and self.minimo > self.maximo:
            raise ValueError('Faixa de campo invalida')
        if self.retangulo and (self.tipo != 'vetor' or self.tamanho != 4):
            raise ValueError('Retangulo exige vetor de quatro coordenadas')
        if self.tipo == 'enum' and (not self.valores or any(len(v) > 64 for v in self.valores)):
            raise ValueError('Enum exige valores curtos e enumerados')
        return self


class Profile(Named):
    dominio: Identifier
    intervalo_esperado_s: int = Field(ge=1, le=31536000)
    tolerancia_intervalos: int = Field(default=3, ge=1, le=100)
    grandezas: dict[Identifier, Measurement] = Field(min_length=1, max_length=100)
    campos: dict[Literal['estado', 'evento'], dict[Identifier, DataField]] = Field(default_factory=dict)
    configuraveis: list[Identifier] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def known_configuration(self):
        if set(self.configuraveis) - set(self.campos.get('estado', {})):
            raise ValueError('Campos configuraveis devem existir no estado relatado')
        return self


class Device(Named):
    site: Identifier
    area: Identifier
    perfil: Identifier


class Area(Named):
    site: Identifier


class DeviceView(Device):
    dominio: Identifier
    mqtt_username: str
    topico_base: str
    ultimo_contato: datetime | None
    credencial_revogada: bool
    status: str
    intervalo_esperado_s: int
    tolerancia_intervalos: int


class Credential(Model):
    usuario: str
    token: str


class CreatedDevice(DeviceView):
    credencial: Credential
    mqtt_aplicacao_pendente: bool


class Revocation(Model):
    revogado: bool
    mqtt_aplicacao_pendente: bool


class Page(Model):
    page: int
    size: int
    total: int
    items: list[dict]
