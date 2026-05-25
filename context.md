# ChMS(prototype) — Church Planning Committee

## Purpose
Replace the existing Excel-based planning committee tracker (`Planning committe.xlsx`) with a web-based system that streamlines task tracking, Sunday service planning, calendar management, and ministry follow-ups for Living Way Church's planning committee.

## Mapping: Excel → System

| Excel Sheet(s) | System Module | Key Features |
|----------------|--------------|--------------|
| Re cap Sunday service | Task notes | Follow-up tracked via task status + comments on sub-program tasks |
| Plan for next Sunday | Sub-program (Programs & Meetings) | Weekly sub-program with role tasks (Coordinators, Ushers, AV, etc.) |
| Programs & meetings + Calander | Calendar | Month grid, color-coded events, date picker |
| Admin & maintenence | Directory + Task Board | Member list + task CRUD |
| Ministries & Projects 1/2/3 | Categories + Task Board | Category list; tasks filterable by category |

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Flask 3.x (Python) | Lightweight, no ORM needed |
| Database | SQLite 3 | Single file, auto-created, WAL mode |
| Templates | Jinja2 | Ships with Flask |
| Styling | Plain CSS | No frameworks; responsive, print styles |
| Auth | Flask sessions + werkzeug | Password hashing, role-based access |
| Charts | Chart.js v4.4.7 | CDN-loaded, dashboard bar chart |

## Key Design Decisions

1. **Multi-user with login** — email login, 3 roles (admin/power_user/viewer), self-registration pending approval.
2. **Derived status not stored** — computed live from child tasks (no sync issues). Cascade: on_hold > suspended > in_progress > open > completed.
3. **Recurrence generation** — daily check via `before_request`, window `[tomorrow, tomorrow+7]`, idempotent via `(parent_id, generation)` uniqueness.
4. **No external notifications** — in-app dashboard alerts only (due reminders, overdue warnings).
5. **Color-coded badges** — Red/Green/Yellow/Blue for status/priority (novice-friendly).
6. **Version number** — `v1.0.0` in footer, set via `app.config["APP_VERSION"]`, exposed as template global `app_version()`.
7. **Fly.io + Docker** — gunicorn deployment with persistent SQLite volume.
7. **Windows .exe build** — GitHub Actions + PyInstaller + UPX compression.

## Architecture

```
chms/
├── app.py                  # Flask application (30+ routes, ~1147 lines)
├── models.py               # SQLite schema + all query functions (~1065 lines)
├── seed.py                 # Reads seed_data.json, populates DB, creates admin user
├── seed_data.json          # JSON seed data replacing sub-programs.xlsx
├── test_all.py             # 114 tests, all pass
├── Dockerfile              # python:3.12-slim + gunicorn
├── fly.toml                # Fly.io config (256MB, ams region, chms_data volume)
├── requirements.txt        # flask, gunicorn
├── context.md              # This file
├── todo.md                 # Task tracker
├── .dockerignore
├── static/
│   └── style.css           # ~500 lines (responsive, badges, print, auth forms)
├── templates/              # 18 Jinja2 templates
│   ├── base.html           # Auth-aware nav, flash messages, delete modal
│   ├── 404.html
│   ├── dashboard.html      # Summary cards, due reminders, chart, schedule modal
│   ├── login.html          # Email + password login
│   ├── register.html       # Self-registration
│   ├── password.html       # Change own password
│   ├── admin_password.html # Admin resets user password
│   ├── users.html          # User list with approve/delete
│   ├── user_form.html      # Admin add/edit user
│   ├── programs.html       # Category cards (status-filterable)
│   ├── category.html       # Sub-program cards per category
│   ├── sub_program.html    # Task list, notes, inline edit, delete modal
│   ├── sub_program_form.html # Add/edit sub-program
│   ├── category_form.html  # Add/edit program category
│   ├── calendar.html       # Month grid + side panel
│   ├── event_form.html     # Add/edit event
│   ├── members.html        # Member directory
│   ├── member_form.html    # Add/edit member
│   ├── import.html         # CSV import form
└── .github/workflows/
    ├── build.yml           # PyInstaller Windows .exe
    └── fly-deploy.yml      # Auto-deploy to Fly.io on push to main
```

## Database Schema (9 tables)

```sql
-- Core tables (models.py:init_db)
members
  id, name, designation, phone, email, created_at

program_categories
  id, name, description, sort_order, created_at

sub_programs
  id, program_category_id FK, title, description, due_date,
  in_charge_id FK(members), recurring_type, add_to_calendar,
  type_flag, notes, parent_id FK(sub_programs), generation, created_at, updated_at

sub_program_members
  id, sub_program_id FK CASCADE, member_id FK CASCADE, UNIQUE pair

tasks
  id, sub_program_id FK CASCADE, title, due_date,
  assigned_to FK(members), status, priority, created_at, completed_at

task_updates
  id, task_id FK CASCADE, note, created_at

events
  id, title, sub_program_id FK, recurring_type, type_flag,
  start_date, notes, created_at

app_config
  key TEXT PK, value TEXT

users
  id, username UNIQUE, email UNIQUE, password_hash,
  role CHECK(admin/power_user/viewer), display_name,
  is_approved, created_at
```

## Route Map

### Auth
| Method | Route | Decorator | Description |
|--------|-------|-----------|-------------|
| GET/POST | `/login` | — | Email + password login |
| GET/POST | `/register` | — | Self-registration (pending approval) |
| GET | `/logout` | — | Clear session |
| GET/POST | `/password` | `@login_required` | Change own password |

### User Management (admin)
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/users` | User list |
| GET/POST | `/users/add` | Create user (auto-approved) |
| GET/POST | `/users/<id>/edit` | Edit user |
| GET/POST | `/users/<id>/password` | Admin reset password |
| POST | `/users/<id>/approve` | Toggle approval |
| POST | `/users/<id>/delete` | Delete (blocks last admin) |

### Dashboard
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Summary cards, due reminders, chart, upcoming schedule |

### Programs
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/programs` | Category cards (optional `?status=` filter) |
| GET | `/programs/<cat_id>` | Sub-programs in category (optional `?status=` filter) |
| GET/POST | `/programs/add` | Add sub-program |
| GET | `/programs/sub/<sub_id>` | Sub-program detail + tasks |
| GET/POST | `/programs/sub/<sub_id>/edit` | Edit sub-program |
| POST | `/programs/sub/<sub_id>/delete` | Delete sub-program |
| POST | `/programs/sub/<sub_id>/note` | Save notes |
| POST | `/programs/sub/<sub_id>/tasks/add` | Add task |
| GET/POST | `/programs/category/add` | Add category |
| POST | `/programs/category/<cat_id>/edit` | Edit category |
| POST | `/programs/category/<cat_id>/delete` | Delete category |

### Tasks
| Method | Route | Description |
|--------|-------|-------------|
| POST | `/tasks/<tid>` | Update task (title, status, assignee, notes) |
| POST | `/tasks/<tid>/delete` | Delete task |
| POST | `/tasks/<tid>/duplicate` | Duplicate task (+7 days) |
| POST | `/tasks/<tid>/toggle` | Quick-complete toggle |

### Calendar
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/calendar` | Month grid |
| GET | `/calendar/event/<eid>` | Event JSON detail |
| GET/POST | `/events/add` | Add event |
| POST | `/events/<eid>/edit` | Edit event |
| POST | `/events/<eid>/delete` | Delete event |

### Members
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/members` | Directory list |
| GET/POST | `/members/add` | Add member |
| GET/POST | `/members/<mid>/edit` | Edit member |
| POST | `/members/<mid>/delete` | Delete member (clears references) |

### Import / Export
| Method | Route | Description |
|--------|-------|-------------|
| GET/POST | `/import` | CSV import (members/tasks/events) |
| GET | `/export/tasks` | CSV export |
| GET | `/export/events` | CSV export |
| GET | `/export/members` | CSV export |

## Auth Decorators

- `@login_required` — redirects to `/login` if not authenticated; rejects unapproved users
- `@require_write` — requires `admin` or `power_user` role
- `@require_admin` — requires `admin` role
- `@app.context_processor injects current_user` — makes `{{ current_user }}` available in all templates

## Code Conventions

### models.py
- Every function opens and closes its own connection
- `get_conn()` returns `sqlite3.Row`-based connections with WAL mode + foreign keys
- `init_db()` is idempotent (uses `CREATE TABLE IF NOT EXISTS`)
- Derived status/priority computed in Python (not stored)
- Recurrence generation uses `(parent_id, generation)` uniqueness to prevent duplicates

### app.py
- Template globals: `today()`, `status_color()`, `priority_color()`, `get_task_updates()`
- Flash messages with categories: `"success"` (green), `"error"` (red)
- `@login_required` / `@require_write` / `@require_admin` decorators on all routes

### Templates (Jinja2)
- All extend `base.html`
- `base.html`: auth-aware nav (hidden when not logged in), flash messages, delete modal
- CSS classes: `.btn`, `.btn-primary/outline/red`, `.badge-open/progress/done/hold/suspended/low/med/high/critical`
- Form pattern: `.form-card` > `.form-group` > `label + input/select`, `.form-row`, `.form-actions`

## Known Limitations & Technical Debt

1. **N+1 query pattern** — Dashboard and category pages run one query per sub-program to get tasks. Acceptable at current scale.
2. **No drag-and-drop** — Task board is table-based, not Kanban-style.
3. **Single timezone** — All dates stored as ISO strings, no timezone handling.
4. **No file attachments** — Cannot attach photos/PDFs to tasks or events.
5. **No audit log** — Changes not tracked per user.

## Setup & Run

```bash
# Requirements
pip install -r requirements.txt

# Run
cd /home/erangadesaram/Documents/Eranga/Docs/CHMS/chms
python3 app.py

# Opens at http://127.0.0.1:5000
# Database auto-created at ~/.chms/chms.db (Linux) or %APPDATA%/ChMS/chms.db (Windows)
```

### First login
- Email: `admin@livingway.church`
- Password: `qazcde@123`

### Environment variables
| Variable | Default | Purpose |
|----------|---------|---------|
| `CHMS_DB_PATH` | `~/.chms/chms.db` | Override database location |
| `CHMS_ADMIN_PASSWORD` | `qazcde@123` | Force-reset admin password on startup |
| `CHMS_DATA_DIR` | `~/.chms` | Override data directory |
| `FLY_APP_NAME` | — | Auto-detects Fly.io deployment |
| `PORT` | `5000` | HTTP port |

### Reset database
```bash
rm -f ~/.chms/chms.db && cd /path/to/chms && python3 app.py
```

## Deployment

### Fly.io
```bash
flyctl auth login
fly volumes create chms_data --region ams --size 1
fly deploy
```

### GitHub Actions auto-deploy
Push to `main` → triggers `.github/workflows/fly-deploy.yml`. Requires `FLY_API_TOKEN` secret in repo.

### Windows .exe
Push to `main` → triggers `.github/workflows/build.yml`. Artifact: `ChMS.exe`.

## Testing
```bash
cd /home/erangadesaram/Documents/Eranga/Docs/CHMS/chms
rm -f test_chms.db && python3 test_all.py
# 114 tests, 0 failures, 0 skipped
```

## Future Enhancement Ideas
1. **Drag-and-drop task board** — Kanban-style column view
2. **File attachments** — attach photos/PDFs to tasks and events
3. **Audit log** — track who changed what and when
4. **Theme settings** — editable church name, logo upload
5. **Email digests** — weekly email with overdue tasks and upcoming schedule
