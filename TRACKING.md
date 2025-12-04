# Shiparr Improvement Tracking

This file tracks the progress of the requested improvements.

## Status Legend
- [ ] Pending
- [x] Completed
- [~] In Progress

## Tasks

### 1. Improve Healthchecks
- [x] Create branch `feature/healthchecks`
- [x] Implement real service availability checks (e.g., HTTP probe, TCP connect)
- [x] Verify service is up after `docker compose up`
- [x] Add tests
- [x] Status: Completed

### 2. Log Management (OOM Prevention)
- [x] Create branch `feature/log-streaming`
- [x] Replace memory storage with streaming/file-based approach
- [x] Use `docker compose logs -fn` or equivalent stream
- [x] Add tests
- [x] Status: Completed

### 3. YAML Validation
- [x] Create branch `feature/yaml-validation`
- [x] Ensure `safe_load` is used
- [x] Implement strict schema validation
- [x] Add tests
- [x] Status: Completed

### 4. Post-Deployment Image Prune
- [x] Create branch `feature/image-prune`
- [x] Add env var configuration for auto-prune
- [x] Execute `docker image prune` after successful deployment if enabled
- [x] Add tests
- [x] Status: Completed

### 5. Path Validation
- [x] Create branch `feature/path-validation`
- [x] Validate paths to prevent traversal (e.g., ensure within allowed directories)
- [x] Add tests
- [x] Status: Completed

### 6. Name Sanitization
- [x] Create branch `feature/name-sanitization`
- [x] Sanitize project and repository names
- [x] Add tests
- [x] Status: Completed

### 7. SQLite Concurrency
- [x] Create branch `feature/sqlite-concurrency`
- [x] Optimize DB access to avoid locking/concurrency issues (WAL mode, etc.)
- [x] Add tests
- [x] Status: Completed

### 8. Git Pull robustness
- [x] Create branch `feature/git-robustness`
- [x] Handle errors, conflicts, network issues, auth failures gracefully
- [x] Add tests
- [x] Status: Completed

### 9. Deployment Queue System
- [x] Create branch `feature/deployment-queue`
- [x] Implement priority queue
- [x] Mutex per project
- [x] Dependency management
- [x] Configurable sequential/parallel deployments
- [x] Add tests
- [x] Status: Completed
