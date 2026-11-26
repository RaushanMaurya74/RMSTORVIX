# AI Workflow Rules — Invoice & Billing System

## Approach
Build this application incrementally using a spec-driven workflow. These context files define product scope, architecture, coding conventions, UI direction and progress. Read them before implementation and keep them synchronized with the code.

## Scoping Rules
- Implement one small, testable feature unit at a time.
- Prioritize a complete vertical slice over disconnected scaffolding.
- Do not combine unrelated features in one change.
- Preserve existing working code; inspect before editing.
- Do not claim a feature works until it has been run or tested.

## Missing Requirements
- Do not invent business rules that are not specified.
- Record unresolved decisions in `progress-tracker.md` under Open Questions.
- Use sensible, clearly documented defaults only for non-critical implementation details.

## Security
- Never commit secrets, API keys, passwords, tokens, or private customer data.
- Validate inputs on the server, not only in the UI.
- Enforce authentication and authorization for protected routes.
- Keep invoice/customer data scoped to the authenticated business/account.
- Avoid logging sensitive data.

## Documentation Sync
Update relevant context files when scope, architecture, conventions, storage, or UI decisions change. Update the progress tracker after every meaningful implementation unit.

## Verification Before Next Unit
1. Feature works end-to-end within its defined scope.
2. Relevant automated tests pass.
3. No architecture or security invariants are violated.
4. Progress tracker is updated.
5. Run the project's relevant build, lint and test commands; report actual results.
