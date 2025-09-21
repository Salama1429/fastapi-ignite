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

**FastAPI-Ignite** Boilerplate is a production-ready FastAPI boilerplate application with a comprehensive set of features for modern web backend development.

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

### Start with Docker:
   ```bash
   docker-compose up -d
   ```

### Setting up locally

1. **Create a virtual environment**:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Set up environment variables**:
   ```bash
   copy .env.example .env
   ```
   Edit the .env file with your configuration. All environment settings are now consolidated in this single file.

4. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

5. Start the API server
   ```bash
   python cli.py api --reload
   ```

6. Run database migrations
   ```bash
   python cli.py db migrate
   ```

7. Start the background worker
   ```bash
   python cli.py worker
   ```

8. Start the scheduler
   ```bash
   python cli.py scheduler
   ```

9. Access the API documentation:
   - Swagger UI: http://localhost:8000/api/docs
   - ReDoc: http://localhost:8000/api/redoc

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