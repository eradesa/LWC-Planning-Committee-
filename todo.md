# ChMS(prototype) Implementation Todo

## ✅ Completed

### Core Schema & Models
- [x] SQLite schema — 9 tables (members, program_categories, sub_programs, sub_program_members, tasks, task_updates, events, app_config, users)
- [x] All CRUD functions in models.py (~1065 lines)
- [x] JSON seed data (seed_data.json) replacing Excel dependency
- [x] openpyxl removed from requirements

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
- [x] Version number in footer (v1.0.0)

### Deployment
- [x] Dockerfile (python:3.12-slim, gunicorn, --preload)
- [x] fly.toml (256MB, ams volume, auto-stop/start)
- [x] .dockerignore
- [x] GitHub Actions: PyInstaller build with UPX
- [x] GitHub Actions: Fly.io auto-deploy on push to main
- [x] requirements.txt (flask, gunicorn)

### Testing
- [x] 114 tests (model CRUD, route responses, workflows, edge cases, auth)
- [x] All tests pass, 0 skipped
- [x] Runs against isolated test_chms.db

---

## 📋 Remaining

### P0 — Fly.io deployment (manual, one-time)
- [ ] `fly volumes create chms_data --region ams --size 1`
- [ ] `fly deploy`

### P0 — GitHub Actions secret
- [ ] Add `FLY_API_TOKEN` secret to repo (needed for auto-deploy)

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
rm -f test_chms.db && python3 test_all.py
# 114 tests, 0 failures
```

### Admin credentials
- Email: `admin@livingway.church` / Password: `qazcde@123`
- Override with `CHMS_ADMIN_PASSWORD` env var

### Project location
- `/home/erangadesaram/Documents/Eranga/Docs/CHMS/chms/`
- Source Excel: `../Planning committe.xlsx`
