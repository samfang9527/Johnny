# Backend API

The MVP backend API is served by `src.main:create_app()`. Health checks remain at the root, while product routes use the `/api` prefix.

## Local Current User

Until production authentication is implemented, API routes resolve the current user from local/test headers:

- `X-Johnny-User-Id`
- `X-Johnny-User-Email`
- `X-Johnny-User-Display-Name`

Write routes so the user id comes from this dependency, not from request bodies. Production SSO can replace this dependency later without changing route handlers.

## Error Format

Validation, not-found, conflict, and domain validation errors use this envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": []
  }
}
```

Successful responses use:

```json
{
  "data": {}
}
```

## Route Groups

- `GET /health`
- `GET /ready`
- `GET /api/me`
- `GET|PUT /api/athlete/profile`
- `GET|POST /api/races`
- `GET|PUT /api/races/{race_id}`
- `GET|POST /api/training-plans`
- `GET /api/training-plans/{plan_id}`
- `PATCH /api/training-plans/{plan_id}/workouts/{workout_id}`
- `GET|POST /api/activities`
- `GET|POST /api/health-metrics/daily`
- `GET /api/today`
- `GET|POST /api/recommendations`
- `POST /api/recommendations/{recommendation_id}/accept`
- `POST /api/recommendations/{recommendation_id}/reject`
- `POST /api/recommendations/{recommendation_id}/edit`
- `POST /api/recommendations/{recommendation_id}/discuss`
- `POST /api/conversations/messages`
- `POST /api/integrations/connections`
- `POST /api/integrations/webhooks/{provider}/{connection_id}`
