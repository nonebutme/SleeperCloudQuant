from dataclasses import asdict
from app.api.contracts import RouteDefinition
from app.schemas.data_center import DataCenterObjectResponse
from app.schemas.indicators import (
    IndicatorDefinitionRequest, IndicatorRegisterRequest, IndicatorValuesRequest,
    IndicatorEnabledRequest, IndicatorFactorRequest, IndicatorFactorRegistrationRequest,
)


def build_indicator_routes(service):
    wrap=DataCenterObjectResponse
    return [
        RouteDefinition('GET','/api/indicators','indicator_definitions',lambda:wrap(service.list_definitions()),None),
        RouteDefinition('POST','/api/indicators','indicator_create',lambda payload:wrap(service.create_definition(**asdict(payload))),IndicatorDefinitionRequest),
        RouteDefinition('GET','/api/indicators/factor-artifacts','indicator_factor_artifacts',lambda:wrap(service.list_factor_artifacts()),None),
        RouteDefinition('GET','/api/indicators/registrations','indicator_registrations',lambda:wrap(service.list_configs()),None),
        RouteDefinition('POST','/api/indicators/registrations','indicator_register',lambda payload:wrap(service.register(**asdict(payload))),IndicatorRegisterRequest),
        RouteDefinition('POST','/api/indicators/registrations/{config_id}/values','indicator_values',
                        lambda payload,config_id:wrap(service.values(config_id,**asdict(payload))),IndicatorValuesRequest),
        RouteDefinition('PUT','/api/indicators/registrations/{config_id}','indicator_enabled',
                        lambda payload,config_id:wrap(service.set_enabled(config_id,payload.enabled)),IndicatorEnabledRequest),
        RouteDefinition('GET','/api/indicators/registrations/{config_id}/strategy-example','indicator_strategy_example',
                        lambda config_id:wrap(service.strategy_example(config_id)),None),
        RouteDefinition('POST','/api/indicators/registrations/{config_id}/factor','indicator_make_factor',
                        lambda payload,config_id:wrap(service.make_factor(config_id,**asdict(payload))),IndicatorFactorRequest),
        RouteDefinition('POST','/api/indicators/factor-artifacts/{artifact_id}/register','indicator_factor_register',
                        lambda payload,artifact_id:wrap(service.register_factor(artifact_id,reason=payload.reason)),IndicatorFactorRegistrationRequest),
    ]
