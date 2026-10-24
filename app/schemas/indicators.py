from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class IndicatorDefinitionRequest:
    name: str = ''
    expression: str = ''
    source_reference: str = ''
    test_cases: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IndicatorRegisterRequest:
    indicator_id: str = ''
    parameters: dict[str, Any] = field(default_factory=dict)
    adjustment: str = 'raw'
    name: str = ''


@dataclass(frozen=True, slots=True)
class IndicatorValuesRequest:
    symbol: str = '000001'
    start_date: str = ''
    end_date: str = ''
    limit: int = 200


@dataclass(frozen=True, slots=True)
class IndicatorEnabledRequest:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class IndicatorFactorRequest:
    output: str = 'value'
    transform: str = 'identity'
    name: str = ''


@dataclass(frozen=True, slots=True)
class IndicatorFactorRegistrationRequest:
    reason: str = ''
