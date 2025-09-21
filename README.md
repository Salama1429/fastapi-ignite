<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="/docs/assets/logo-main.png">
    <source media="(prefers-color-scheme: light)" srcset="/docs/assets/logo-main.png">
    <img alt="FastAPI-Ignite Boilerplate " src="/docs/assets/logo-main.png" width="158" height="326" style="max-width: 100%;">
  </picture>
  <br/>
</p>

<p align="center">
   <h2 align="center">FastAPI-Ignite Boilerplate </h2>
</p>

**FastAPI-Ignite** Boilerplate is a production-ready FastAPI boilerplate application with a comprehensive set of features for modern web backend development. It demonstrates multi-tenant subscription management, retrieval-augmented generation (RAG) workflows, caching, rate limiting, and integrations with PostgreSQL, Redis, and OpenAI.

## Core Technologies

- **FastAPI**: High-performance async web framework for building APIs
- **SQLAlchemy**: SQL toolkit and ORM with async support
- **Pydantic v2**: Data validation and settings management using Python type hints
- **PostgreSQL**: Powerful open-source relational database
- **Redis**: In-memory data store for caching and message broker
- **Dramatiq**: Distributed task processing for background jobs
- **APScheduler**: Advanced Python scheduler for periodic tasks
- **Alembic**: Database migration tool

## Features

- ✅ **Modern Python codebase** using async/await syntax
- ✅ **Structured project layout** for maintainability
- ✅ **API versioning** to manage API evolution
- ✅ **Database integration** with async SQLAlchemy 2.0
- ✅ **Background task processing** with Dramatiq
- ✅ **Scheduled tasks** with APScheduler
- ✅ **Simple configuration** using environment variables
- ✅ **Comprehensive logging** with structured logs
- ✅ **Docker support** for easy deployment
- ✅ **Database migrations** with Alembic
- ✅ **Production-ready** with health checks, error handling, and more
- ✅ **Advanced caching** with multiple backends (Redis, File, Memory) at function and API endpoint levels

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/bakrianoo/fastapi-ignite.git
   cd fastapi-ignite
   ```

2. Set up environment:
   ```bash
   # Copy the example .env file and edit with your configuration
   cp .env.example .env
   ```

### Start with Docker

```bash
docker-compose up -d
```

### Setting up locally

1. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   ```
   Edit the `.env` file with your configuration. All environment settings are consolidated in this single file.

4. **Run database migrations** (choose one):
   ```bash
   alembic upgrade head
   ```
   or
   ```bash
   python cli.py db migrate
   ```

5. **Start the API server**
   ```bash
   python cli.py api --reload
   ```

6. **Start the background worker** (optional)
   ```bash
   python cli.py worker
   ```

7. **Start the scheduler** (optional)
   ```bash
   python cli.py scheduler
   ```

8. **Access the API documentation**:
   - Swagger UI: http://localhost:8000/api/docs
   - ReDoc: http://localhost:8000/api/redoc

## Application architecture at a glance

- `main.py` instantiates the FastAPI application, configures metadata, enables CORS, mounts the versioned `/api` router, and wires startup/shutdown hooks so dependencies (database, cache, schedulers) can warm up gracefully.
- `src/api/v1/router.py` composes the v1 API by including the domain routers (`items`, `billing`, `ingestion`, `query`, `limits`, and `tenants`) and exposes lightweight health and application metadata endpoints.
- Configuration is centralized in `src/core/config.py`, which provides typed settings for API host/port, database URIs, cache backends, scheduler flags, OpenAI credentials, JWT secrets, and rate limit values.
- Domain logic is layered behind services and repositories:
  - `src/services/item_service.py` and `src/services/cached_item_service.py` encapsulate CRUD and caching strategies for demo items.
  - `src/services/openai_service.py` wraps OpenAI vector store and Responses APIs.
  - Repository classes (`src/repositories/*.py`) isolate database access for plans, subscriptions, tenants, projects, and usage counters.

## Authentication, rate limiting, and quotas

- Endpoints under `/billing`, `/ingestion`, `/query`, and `/limits` require a Bearer token. The token must be a JWT signed with `JWT_SECRET` and include a `tenant_id` claim; `require_auth` validates the header and converts the tenant into a UUID before the request body is processed.
- Rate limiting and idempotency are enforced per tenant via Redis. `check_rate_limit` allows `RATE_LIMIT_RPM` requests (120 by default) per tenant per minute, while `ensure_idempotent` rejects duplicate POSTs that share the same `Idempotency-Key` header within a 30 minute window.
- Subscription quotas are enforced everywhere a tenant consumes resources:
  - Plans define `max_projects`, `monthly_message_cap`, and `monthly_upload_char_cap`.
  - `SubscriptionRepo` tracks the active plan and the billing window for each tenant.
  - `UsageRepo` aggregates daily counters for message usage and uploaded characters so the ingestion and query endpoints can stop tenants from exceeding their caps before work is sent to OpenAI.
- To mint a JWT for local testing you can use the following helper (replace the secret and tenant ID as appropriate):
  ```bash
  python - <<'PY'
  import jwt, uuid
  tenant_id = str(uuid.uuid4())  # replace with a real tenant ID
  token = jwt.encode({"tenant_id": tenant_id}, "change-me", algorithm="HS256")
  print(token)
  PY
  ```
- Redis is also the default cache backend (`CACHE_BACKEND_TYPE=redis`) with a 5 minute default TTL (`CACHE_TTL_SECONDS=300`). Item endpoints demonstrate how function-level caching and manual cache invalidation work.

## API reference

All endpoints are versioned under `/api/v1`. The examples below assume:

```bash
export BASE_URL=http://localhost:8000
export API_V1=$BASE_URL/api/v1
export TOKEN="eyJhbGciOi..."         # JWT containing a tenant_id claim
export TENANT_ID="00000000-0000-0000-0000-000000000000"  # replace with a real tenant ID
```

Authenticated requests add `-H "Authorization: Bearer $TOKEN"`.

### Health & metadata

#### GET `/api/v1/health`

*Logic*

- Returns a static payload confirming the API is reachable.

*Example*

```bash
curl "$API_V1/health"
```

*Response*

```json
{
  "status": "ok",
  "version": "1"
}
```

#### GET `/api/v1/app-info`

*Logic*

- Surfaces the configured project name, description, and semantic version.

*Example*

```bash
curl "$API_V1/app-info"
```

*Response*

```json
{
  "name": "FastAPI-Ignite",
  "description": "A FastAPI application",
  "version": "0.1.0"
}
```

### Item catalog (public demo)

These endpoints are unauthenticated and showcase CRUD with layered services plus cache integrations.

#### POST `/api/v1/items/`

*Logic*

- Accepts an `ItemCreate` payload, persists it with `ItemService.create_item`, and returns the stored record including server-side timestamps.

*Example*

```bash
curl -X POST "$API_V1/items/" \
  -H "Content-Type: application/json" \
  -d '{"name":"Notebook","description":"Plain pages","is_active":true}'
```

*Response*

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "name": "Notebook",
  "description": "Plain pages",
  "is_active": true,
  "created_at": "2024-06-02T12:34:56.123456",
  "updated_at": "2024-06-02T12:34:56.123456"
}
```

#### GET `/api/v1/items/{item_id}`

*Logic*

- Reads an item by UUID, caching the response for `CACHE_TTL_SECONDS` (5 minutes by default).
- Raises a 404 if the item does not exist.

*Example*

```bash
curl "$API_V1/items/f47ac10b-58cc-4372-a567-0e02b2c3d479"
```

*Response*

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "name": "Notebook",
  "description": "Plain pages",
  "is_active": true,
  "created_at": "2024-06-02T12:34:56.123456",
  "updated_at": "2024-06-02T12:34:56.123456"
}
```

#### GET `/api/v1/items/`

*Logic*

- Supports pagination (`skip`, `limit`) and filtering (`active_only`) while caching list responses for 60 seconds.
- Delegates to `ItemService.get_items` so results are ordered by creation time and optional active flag.

*Example*

```bash
curl "$API_V1/items/?skip=0&limit=10&active_only=true"
```

*Response*

```json
[
  {
    "id": "0c5c9d69-2f06-4a2a-9d98-2d8c2f1df111",
    "name": "Notebook",
    "description": "Plain pages",
    "is_active": true,
    "created_at": "2024-06-02T12:34:56.123456",
    "updated_at": "2024-06-02T12:34:56.123456"
  }
]
```

#### PUT `/api/v1/items/{item_id}`

*Logic*

- Applies partial updates from an `ItemUpdate` payload and returns the refreshed record.
- The service filters out `null` fields so unspecified attributes are not overwritten.

*Example*

```bash
curl -X PUT "$API_V1/items/f47ac10b-58cc-4372-a567-0e02b2c3d479" \
  -H "Content-Type: application/json" \
  -d '{"description":"Lined pages"}'
```

*Response*

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "name": "Notebook",
  "description": "Lined pages",
  "is_active": true,
  "created_at": "2024-06-02T12:34:56.123456",
  "updated_at": "2024-06-02T13:05:10.654321"
}
```

#### DELETE `/api/v1/items/{item_id}`

*Logic*

- Removes the item after verifying it exists. Returns HTTP 204 with no body.

*Example*

```bash
curl -X DELETE -i "$API_V1/items/f47ac10b-58cc-4372-a567-0e02b2c3d479"
```

*Response*

```
HTTP/1.1 204 No Content
```

#### GET `/api/v1/items/search/`

*Logic*

- Performs a case-insensitive search across item names and descriptions using SQL `ILIKE`.
- Supports the same pagination parameters as the list endpoint.

*Example*

```bash
curl "$API_V1/items/search/?q=note&limit=5"
```

*Response*

```json
[
  {
    "id": "0c5c9d69-2f06-4a2a-9d98-2d8c2f1df111",
    "name": "Notebook",
    "description": "Plain pages",
    "is_active": true,
    "created_at": "2024-06-02T12:34:56.123456",
    "updated_at": "2024-06-02T12:34:56.123456"
  }
]
```

#### GET `/api/v1/items/cached/{item_id}`

*Logic*

- Demonstrates direct cache usage: looks up the item in the configured cache backend, falls back to the database, and stores a JSON copy for future requests.

*Example*

```bash
curl "$API_V1/items/cached/f47ac10b-58cc-4372-a567-0e02b2c3d479"
```

*Response*

```json
{
  "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "name": "Notebook",
  "description": "Lined pages",
  "is_active": true,
  "created_at": "2024-06-02T12:34:56.123456",
  "updated_at": "2024-06-02T13:05:10.654321"
}
```

#### GET `/api/v1/items/cache/clear`

*Logic*

- Scans cache keys matching `item:*` and deletes them. Useful when testing cache invalidation.

*Example*

```bash
curl "$API_V1/items/cache/clear"
```

*Response*

```json
{
  "message": "Successfully cleared 3 cached items",
  "deleted_count": 3
}
```

### Tenant bootstrap

#### POST `/api/v1/tenants/create`

*Logic*

- Validates the requested billing cycle, fetches the referenced plan, creates a tenant, and seeds an initial subscription covering the next billing period.
- The response includes the tenant ID along with the active plan limits.

*Example*

```bash
curl -X POST "$API_V1/tenants/create?name=Acme%20Co&plan_id=hobby&billing_cycle=monthly"
```

*Response*

```json
{
  "tenant_id": "2cb9e69e-6fe7-4f5c-8f4d-5a9c6a2bd5d4",
  "plan_id": "hobby",
  "plan_name": "Hobby",
  "billing_cycle": "monthly",
  "period_start": "2024-06-01",
  "period_end": "2024-06-30",
  "limits": {
    "max_projects": 3,
    "monthly_message_cap": 2000,
    "monthly_upload_char_cap": 500000
  }
}
```

### Billing

#### POST `/api/v1/billing/subscribe`

*Logic*

- Requires authentication.
- Verifies the billing cycle, enforces the per-tenant rate limit, fetches the requested plan, upserts the tenant's subscription window, and syncs the tenant record's cached plan metadata.

*Example*

```bash
curl -X POST "$API_V1/billing/subscribe?plan_id=pro&cycle=annual" \
  -H "Authorization: Bearer $TOKEN"
```

*Response*

```json
{
  "status": "ok",
  "plan_id": "pro",
  "plan_name": "Pro",
  "billing_cycle": "annual",
  "period_start": "2024-06-01",
  "period_end": "2025-05-31",
  "limits": {
    "max_projects": 10,
    "monthly_message_cap": 20000,
    "monthly_upload_char_cap": 2000000
  }
}
```

### Ingestion workflow

These endpoints assume the tenant already has an active subscription and the plan's quotas are not exceeded.

#### POST `/api/v1/ingestion/projects/create`

*Logic*

- Requires authentication and a matching `tenant_id` query parameter.
- Rejects mismatched tenants, checks the rate limit, ensures the tenant has an active subscription, returns `status=exists` if the project name is already used, and enforces the plan's `max_projects` limit before creating a project.

*Example*

```bash
curl -X POST "$API_V1/ingestion/projects/create?tenant_id=$TENANT_ID&name=Docs" \
  -H "Authorization: Bearer $TOKEN"
```

*Response*

```json
{
  "id": "f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b",
  "tenant_id": "2cb9e69e-6fe7-4f5c-8f4d-5a9c6a2bd5d4",
  "name": "Docs",
  "vector_store_id": null,
  "status": "created"
}
```

#### POST `/api/v1/ingestion/projects/{project_id}/ensure_vector_store`

*Logic*

- Requires authentication and matching tenant.
- Creates a new OpenAI vector store (via `create_vector_store`) if one is not already linked to the project; otherwise returns the existing ID.

*Example*

```bash
curl -X POST "$API_V1/ingestion/projects/f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b/ensure_vector_store?tenant_id=$TENANT_ID" \
  -H "Authorization: Bearer $TOKEN"
```

*Response*

```json
{
  "project_id": "f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b",
  "vector_store_id": "vs_abc123",
  "status": "created"
}
```

#### POST `/api/v1/ingestion/projects/{project_id}/upload_and_attach`

*Logic*

- Requires authentication, matching tenant, and at least one uploaded file (`multipart/form-data` with `files` fields).
- Calculates the character count of uploaded files, validates the tenant still has an active subscription, checks against the plan's `monthly_upload_char_cap`, uploads the files to OpenAI, attaches them to the vector store as a batch, and records usage stats.

*Example*

```bash
curl -X POST "$API_V1/ingestion/projects/f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b/upload_and_attach?tenant_id=$TENANT_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -F "files=@docs/guide.txt"
```

*Response*

```json
{
  "project_id": "f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b",
  "vector_store_id": "vs_abc123",
  "batch_status": "completed",
  "file_counts": {
    "processed": 1
  }
}
```

#### GET `/api/v1/ingestion/projects/{project_id}/files`

*Logic*

- Requires authentication and matching tenant.
- Lists files currently attached to the project's vector store and normalizes the OpenAI SDK response into plain dictionaries.

*Example*

```bash
curl "$API_V1/ingestion/projects/f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b/files?tenant_id=$TENANT_ID" \
  -H "Authorization: Bearer $TOKEN"
```

*Response*

```json
{
  "project_id": "f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b",
  "vector_store_id": "vs_abc123",
  "files": [
    {
      "id": "file_1",
      "filename": "guide.txt",
      "status": "completed"
    }
  ]
}
```

#### DELETE `/api/v1/ingestion/projects/{project_id}/remove_file`

*Logic*

- Requires authentication and matching tenant.
- Removes the specified file from the vector store and, if `delete_raw=true`, deletes the original upload from OpenAI storage.

*Example*

```bash
curl -X DELETE "$API_V1/ingestion/projects/f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b/remove_file?tenant_id=$TENANT_ID&openai_file_id=file_1&delete_raw=false" \
  -H "Authorization: Bearer $TOKEN"
```

*Response*

```json
{
  "project_id": "f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b",
  "vector_store_id": "vs_abc123",
  "removed_file_id": "file_1",
  "delete_raw": false
}
```

### Query

#### POST `/api/v1/query/ask`

*Logic*

- Requires authentication, matching project/tenant, an `Idempotency-Key` header for duplicate detection (optional but recommended), and a JSON payload containing `project_id` and `question`.
- Verifies the tenant has an active subscription, enforces the plan's `monthly_message_cap`, logs both the user question and assistant answer to the `messages` table, invokes OpenAI Responses with File Search, tallies token usage, and returns the answer plus any extracted citations.

*Example*

```bash
curl -X POST "$API_V1/query/ask" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: query-001" \
  -d '{"project_id":"f110f5f6-33a3-4e72-9f8f-84cc0f5f5c0b","question":"What does the onboarding guide cover?"}'
```

*Response*

```json
{
  "answer": "The onboarding guide covers the account setup checklist.",
  "tokens_in": 128,
  "tokens_out": 64,
  "citations": [
    {
      "file_id": "file_1",
      "quote": "Step one of onboarding is connecting your account."
    }
  ]
}
```

### Subscription limits

#### GET `/api/v1/limits/current`

*Logic*

- Requires authentication.
- Enforces rate limiting, fetches the tenant's subscription, and returns both plan limits and current usage counts (projects, messages, uploaded characters). If the tenant has no active subscription the response is `{ "subscribed": false }`.

*Example*

```bash
curl "$API_V1/limits/current" \
  -H "Authorization: Bearer $TOKEN"
```

*Response*

```json
{
  "subscribed": true,
  "plan_id": "pro",
  "plan_name": "Pro",
  "billing_cycle": "annual",
  "period_start": "2024-06-01",
  "period_end": "2025-05-31",
  "limits": {
    "max_projects": 10,
    "monthly_message_cap": 20000,
    "monthly_upload_char_cap": 2000000
  },
  "usage": {
    "projects": 2,
    "messages_used": 15,
    "chars_uploaded": 12000
  }
}
```

## Development

See [DEVELOPER GUIDE](DEVELOPER-GUIDE.md) for detailed development information.

## Integrating a Shipfa.st Next.js Frontend

The project plays well with modern TypeScript frontends such as the [shipfa.st Next.js boilerplate](https://shipfa.st/). A typical integration flow looks like this:

1. **Configure shared environment variables**
   - Expose the FastAPI base URL (e.g., `http://localhost:8000/api`) to the Next.js app via `NEXT_PUBLIC_API_BASE_URL`.
   - Add authentication secrets (e.g., JWT signing secret) to both the backend `.env` file and the Shipfa.st `.env.local` file so the frontend can mint or validate session tokens as needed.

2. **Generate typed API clients**
   - Run `pnpm openapi-typescript` (or your preferred generator) against the FastAPI OpenAPI schema at `http://localhost:8000/api/openapi.json` to create reusable TypeScript clients in the Shipfa.st app.
   - Consider colocating the generated clients under `apps/web/lib/api` and re-running the generator as part of the frontend build step to keep SDKs up to date.

3. **Implement tenant-aware fetch helpers**
   - In the Next.js app, wrap `fetch` (or `@tanstack/query` hooks) to automatically attach tenant headers (e.g., `Authorization: Bearer <jwt>` or custom `X-Tenant-Id` headers) for every request to the FastAPI backend.
   - Store active project or tenant identifiers in Shipfa.st's global state (Zustand/Redux) or in URL segments so each page shares consistent context when calling ingestion or query endpoints.

4. **Leverage Shipfa.st UI primitives**
   - Use the boilerplate's dashboard layout and component library to surface onboarding flows (project creation, file uploads, quota displays) that correspond to the backend endpoints under `/api/v1/ingestion`, `/api/v1/query`, `/api/v1/limits`, and `/api/v1/billing`.
   - Bridge real-time status updates (upload progress, query responses) with Shipfa.st's built-in toast/notification system for cohesive UX feedback.

5. **Local development workflow**
   - Start the FastAPI server with `python cli.py api --reload` and the Next.js app with `pnpm dev` (or `npm run dev`) in the Shipfa.st repository.
   - Enable CORS for the frontend origin by setting `BACKEND_CORS_ORIGINS` in `.env` (comma-separated list). This allows the Next.js dev server to access FastAPI endpoints without manual proxying.

Document any additional integration steps that are specific to your deployment (e.g., shared authentication providers, deployment pipelines) so the backend and frontend teams can stay aligned.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
