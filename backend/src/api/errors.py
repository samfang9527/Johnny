from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from src.domain.activity_health import DomainValidationError as ActivityHealthValidationError
from src.domain.athlete_race import DomainValidationError as AthleteRaceValidationError
from src.domain.integrations_notifications import DomainValidationError as IntegrationsNotificationsValidationError
from src.domain.recommendation_approval import DomainValidationError as RecommendationValidationError
from src.domain.training_plan import DomainValidationError as TrainingPlanValidationError


class ApiNotFoundError(ValueError):
    pass


class ApiConflictError(ValueError):
    pass


class ApiUnauthorizedError(ValueError):
    pass


DOMAIN_ERRORS = (
    ActivityHealthValidationError,
    AthleteRaceValidationError,
    IntegrationsNotificationsValidationError,
    RecommendationValidationError,
    TrainingPlanValidationError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="validation_error",
            message="Request validation failed",
            details=_validation_details(exc),
        )

    @app.exception_handler(ApiNotFoundError)
    async def not_found_exception_handler(request: Request, exc: ApiNotFoundError) -> JSONResponse:
        return _error_response(status_code=404, code="not_found", message=str(exc), details=[])

    @app.exception_handler(ApiConflictError)
    async def conflict_exception_handler(request: Request, exc: ApiConflictError) -> JSONResponse:
        return _error_response(status_code=409, code="conflict", message=str(exc), details=[])

    @app.exception_handler(ApiUnauthorizedError)
    async def unauthorized_exception_handler(request: Request, exc: ApiUnauthorizedError) -> JSONResponse:
        return _error_response(status_code=401, code="unauthorized", message=str(exc), details=[])

    for error_type in DOMAIN_ERRORS:
        app.add_exception_handler(error_type, domain_validation_exception_handler)


async def domain_validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _error_response(
        status_code=400,
        code="domain_validation_error",
        message=str(exc),
        details=[],
    )


def _error_response(*, status_code: int, code: str, message: str, details: list) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def _validation_details(exc: RequestValidationError) -> list:
    details = []
    for error in exc.errors():
        normalized = dict(error)
        ctx = normalized.get("ctx")
        if isinstance(ctx, dict):
            normalized["ctx"] = {key: str(value) for key, value in ctx.items()}
        details.append(normalized)
    return jsonable_encoder(details)
