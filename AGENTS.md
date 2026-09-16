# LinkToon engineering guide

## Stack and source of truth

- Frontend: Next.js 16, React, TypeScript in `apps/web`.
- Backend: FastAPI, Python 3.12, SQLAlchemy and Alembic in `apps/api`.
- Production data: Supabase PostgreSQL, Auth and private Storage.
- Planned AI providers: OpenAI, fal.ai and Runway, called by the backend only.
- The checked-out workspace is the source of truth. Preserve working features and existing API contracts.

## Required architecture

`Frontend -> FastAPI -> Service -> AI Router -> Provider adapter`

- Never call an AI provider directly from frontend code.
- Never expose provider keys, database credentials or the Supabase service-role key to the browser.
- All AI work must enter through the backend `GenerationService`, which applies the database-backed daily quota and creates a `GenerationJob`.
- Store generated files as new `Asset` rows and immutable storage objects. Never overwrite an original asset.
- Keep provider-specific request, polling and error translation code inside its provider adapter.
- Use Alembic for every database schema change.
- Use owner-scoped repository queries for private resources.
- Keep Supabase Storage private and return short-lived API capability URLs.

## Change discipline

Run frontend lint, typecheck, tests and production build. Run backend Ruff, mypy, pytest, Alembic drift checks and PostgreSQL integration tests for database or RLS changes. Do not describe future AI, Motion, Reader or Publish work as implemented.

Repository documents use existing lowercase names on this Windows workspace: `docs/product-spec.md`, `docs/architecture.md`, `docs/database.md`, `docs/api.md` and `docs/ai-providers.md`. Deployment instructions are in `docs/DEPLOYMENT.md`.
