# Vibecoding Board Optimization Plan

## Goal
Optimize the `vibecoding-board` project step-by-step according to the previous analysis, focusing on performance, code quality, and robustness.

## Phases

### Phase 1: Fix Backend Event Loop Blocking (Performance)
- [ ] Refactor `config_store.py` to use `asyncio.to_thread` for the `save` method to prevent blocking the FastAPI event loop during file IO.

### Phase 2: Split Frontend "God Component" `App.tsx` (Code Quality)
- [ ] Extract Dashboard logic into custom hooks.
- [ ] Extract Provider management into hooks/components.
- [ ] Extract Metrics/Toasts into separate components.

### Phase 3: Fine-grain Global Lock in ProviderRegistry (Performance)
- [ ] Refactor `registry.py` to use per-provider locks or optimize the global lock contention during high concurrency proxying.

### Phase 4: Implement Exponential Backoff for Retries (Robustness)
- [ ] Update `service.py` `RetryPolicyConfig` and proxy logic to use exponential backoff instead of fixed intervals.

### Phase 5: Enhance Backend Background Tasks Lifecycle (Robustness)
- [ ] Update `ManagedUpstreamWebSocketSession` in `service.py` to ensure `try-finally` cleanup for background tasks or use `asyncio.TaskGroup`.

### Phase 6: Add Frontend Error Boundaries & I18n Refactor (Code Quality & UX)
- [ ] Wrap React app with `ErrorBoundary`.
- [ ] Refactor `api.ts` `currentLocale` to use React Context dynamically.

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|

