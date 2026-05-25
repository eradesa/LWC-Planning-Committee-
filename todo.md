# ChMS(prototype) Implementation Todo

## ✅ Completed

### Core Schema & Models
- [x] PostgreSQL schema — 9 tables (members, program_categories, sub_programs, sub_program_members, tasks, task_updates, events, app_config, users)
- [x] All CRUD functions in models.py (~1197 lines)
- [x] psycopg2 with _Connection wrapper, RealDictCursor, DATABASE_URL env var
- [x] SQLite removed — ? → %s, datetime('now') → TO_CHAR(CURRENT_TIMESTAMP, ...), SERIAL PKs

### User Management (Multi-user)
- [x] Login with email + password
- [x] Self-registration with pending approval
- [x] 3 roles: admin / power_user / viewer
- [x] Admin user management (list, add, edit, approve, delete, reset password)
- [x] Change own password
- [x] Block unapproved users
- [x] Role-gated decorators (@login_required, @require_write, @require_admin)
- [x] All existing routes protected
- [x] Seeded admin: admin@livingway.church / qazcde@123

### Programs & Sub-Programs
- [x] Program categories with sort order
- [x] Sub-programs with derived status/priority from child tasks
- [x] Type flags (Program / Meeting / Event / Service)
- [x] Recurring sub-programs (weekly/bi-weekly/monthly/quarterly/annual)
- [x] Daily recurrence check via before_request
- [x] Recurrence window: [tomorrow, tomorrow+7]
- [x] Auto-run recurrence on save (force=True)
- [x] Edit-block: changing due_date/recurring_type on base with children
- [x] Generated child instances linked via parent_id + generation
- [x] Tasks copied to children with shifted due_dates, status reset to open
- [x] Delete cascade: children deleted when base deleted

### Tasks
- [x] Full CRUD with status, priority, assigned_to, due_date
- [x] Server-side due_date validation (task ≤ parent sub-program)
- [x] Quick-complete toggle (open ↔ completed)
- [x] Duplicate task (+7 days, "(copy)" suffix)
- [x] Inline edit (title, due_date, assignee, priority, status)
- [x] Follow-up notes (task_updates table)
- [x] Pagination on sub-program detail (50 per page)
- [x] Status select with auto-submit

### Calendar & Events
- [x] Month grid calendar view
- [x] Event CRUD with type flags + recurrence
- [x] Recurring events expanded on-the-fly (no stored instances)
- [x] Next recurrence dates shown on save
- [x] Event date ≤ linked sub-program due_date (validated)
- [x] Event detail modal on dashboard schedule

### Dashboard
- [x] Summary cards (total/open/in-progress/completed/hold/overdue)
- [x] Cards link to filtered program views (?status= param)
- [x] Due Today / Due This Week reminders
- [x] Chart.js bar chart (tasks by status)
- [x] Upcoming Schedule (scrollable, event detail modal)
- [x] Active sub-programs table with search + sort
- [x] Overdue sub-programs table
- [x] Export links (CSV)

### Import / Export
- [x] CSV import (members, tasks, events)
- [x] CSV export (tasks, events, members)

### UI Polish
- [x] Responsive mobile-friendly layout
- [x] Delete confirmation modals (styled, not browser confirm())
- [x] Pagination with prev/next links
- [x] CSS print styles
- [x] Loading spinner overlay
- [x] 404 error page
- [x] Orphaned reference cleanup on delete (members, categories)
- [x] Color-coded status/priority badges
- [x] Version number in footer (v1.1.0)

### Database Migration (SQLite → PostgreSQL)
- [x] models.py rewritten: psycopg2, _Connection wrapper, SERIAL PKs
- [x] app.py cleaned: ? → %s, datetime('now') → TO_CHAR, removed SQLite/Win/PyInstaller cruft
- [x] test_all.py: TRUNCATE ... RESTART IDENTITY, PG-compatible assertions
- [x] requirements.txt: flask, gunicorn, psycopg2-binary
- [x] seed.py + seed_data.json removed (inline test data)
- [x] All 114 tests pass against PostgreSQL 14

### Deployment
- [x] Dockerfile (python:3.12-slim, gunicorn, --bind 0.0.0.0:5000)
- [x] fly.toml (256MB, sin region, no volume)
- [x] .dockerignore
- [x] GitHub Actions: Fly.io auto-deploy on push to main (needs FLY_API_TOKEN secret)
- [x] requirements.txt (flask, gunicorn, psycopg2-binary)
- [x] Deployed to Fly.io (Singapore) + Neon PostgreSQL (Singapore)
- [x] Old Fly volumes cleaned up

### Testing
- [x] 114 tests (model CRUD, route responses, workflows, edge cases, auth)
- [x] All tests pass on PostgreSQL, 0 skipped
- [x] Runs against isolated chms_test database

---

## ⚠️ Remaining

### P1 — GitHub Actions
- [ ] Add `FLY_API_TOKEN` secret to GitHub repo (needed for auto-deploy on push to main)

### P2 — Polish
- [ ] Update context.md to reflect PostgreSQL architecture

---

## 📝 Notes

### How data flows
1. `models.py:init_db()` auto-runs on import → creates all 9 tables
2. `app.py` imports all functions from `models.py`
3. Auth decorators gate every route by role
4. Recurrence check runs on `before_request`, first request each day
5. Derived status/priority computed live (not stored)

### Where to add a new feature
- **New DB table** → add `CREATE TABLE` to `init_db()` in `models.py`
- **New query function** → add to `models.py`, export at top
- **New route** → add to `app.py` with `@app.route` + appropriate auth decorator
- **New template** → create in `templates/`, extend `base.html`
- **New CSS** → add classes to `static/style.css`

### Testing
```bash
cd /home/erangadesaram/Documents/Eranga/Docs/CHMS/chms
DATABASE_URL="dbname=chms_test host=/tmp port=15432 user=erangadesaram" python3 -m pytest test_all.py -v
# 114 tests, 0 failures
```

### Run locally
```bash
DATABASE_URL="dbname=chms_dev host=/tmp port=15432 user=erangadesaram" python3 app.py
# Opens at http://127.0.0.1:5000
```

### Admin credentials
- Email: `admin@livingway.church` / Password: `qazcde@123`
- Override with `CHMS_ADMIN_PASSWORD` env var

### Project location
- `/home/erangadesaram/Documents/Eranga/Docs/CHMS/chms/`
- Source Excel: `../Planning committe.xlsx`
