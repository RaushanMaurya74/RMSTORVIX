# Code Standards — Invoice & Billing System

## General
- Keep modules focused, small and maintainable.
- Fix root causes instead of adding fragile workarounds.
- Use descriptive names and document non-obvious business rules.
- Avoid duplication; share reusable logic where appropriate.

## Python / FastAPI
- Use type annotations and Pydantic schemas for API boundaries.
- Validate external input before business logic.
- Keep route handlers thin; put domain logic in services.
- Use async only where the selected libraries and workload justify it.
- Use structured, consistent API response and error patterns.
- Never expose stack traces or secrets to end users.

## Frontend
- Use accessible semantic HTML and responsive CSS.
- Keep JavaScript modular and avoid large monolithic scripts.
- Handle loading, empty, success and error states.
- Validate client-side for usability, but always validate again on the server.
- Avoid unsafe DOM insertion; sanitize or safely render untrusted text.

## API Routes
- Validate request bodies, path and query parameters.
- Enforce authentication, ownership and role authorization before mutations.
- Use appropriate HTTP status codes.
- Avoid leaking whether sensitive records exist to unauthorized callers.

## Data and Storage
- Use migrations for schema changes.
- Use transactions for operations that must succeed or fail together.
- Use parameterized ORM/database operations.
- Store secrets outside source code.
- Do not log passwords, authentication tokens or sensitive customer data.

## Testing
- Add tests for services, routes and important business calculations.
- Include authorization, invalid input, edge cases and transaction behavior.
- Run tests after each feature and report failures honestly.

## File Organization
Follow `architecture.md`. Do not create sprawling files or modify third-party library internals.
