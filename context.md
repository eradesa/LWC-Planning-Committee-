# ChMS(prototype) — Church Planning Committee

## Purpose
Replace the existing Excel-based planning committee tracker (`Planning committe.xlsx`) with a web-based system that streamlines task tracking, Sunday service planning, calendar management, and ministry follow-ups for Living Way Church's planning committee.

## Original Excel Analysis

The source file `Planning committe.xlsx` contained **8 sheets** with the following characteristics:

| Sheet | Rows | Columns | Purpose | Key Issues |
|-------|------|---------|---------|------------|
| Re cap Sunday service | 2733 (~20 used) | 9 | Weekly post-service issues & follow-ups | 99% empty rows; mixed date formats; no status/assignee |
| Plan for next Sunday | 73 | 8 | Pre-service role assignments | Static "To be filled" text; no actual data |
| Programs & meetings | 22 | 12 | Quarterly recurring program scheduling | Only Q1/Q2 visible; no link to calendar |
| Calander | 21 | 6 | Master church event list | No actual dates; static checklist |
| Admin & maintenence | 36 | 3 | Pastor/leader tasks & maintenance | Mostly empty; no priority/status |
| Ministries & Projects 1 | 36 | 6 | New Comers, JDC, ChMS, YA, Mens | 3 separate sheets for same concept |
| Ministries & projects 2 | 37 | 6 | Women, Missions, Disaster Relief, SS, Teens | Same issues as above |
| Ministries & projects 3 | 37 | 6 | Alpha Marriage, Sanctuary | Same issues as above |

### Cross-cutting Excel Problems
- No access control or audit trail
- No status tracking (open/in-progress/done)
- No assignee or priority
- Inconsistent date formats
- No search/filter across 2733 rows
- No mobile access
- No centralized calendar

## Mapping: Excel → System

| Excel Sheet(s) | System Module | Key Features |
|----------------|--------------|--------------|
| Re cap Sunday service | Sunday Recap | Date-based form with per-item notes + general notes |
| Plan for next Sunday | Sunday Plan | Role-by-role assignment for upcoming Sundays |
| Programs & meetings + Calander | Calendar | Month grid, color-coded events, date picker |
| Admin & maintenence | Directory + Task Board | Member list + task CRUD |
| Ministries & Projects 1/2/3 | Ministries + Task Board | Ministry list; tasks filterable by ministry |

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Backend | Flask 3.x (Python) | Lightweight, no ORM needed |
| Database | SQLite 3 | Single file (`chms.db`), auto-created |
| Templates | Jinja2 | Ships with Flask |
| Styling | Plain CSS | No frameworks; matches lwc-salary-system theme |
| PDF | reportlab | Available in requirements but not yet used |

## Key Design Decisions

1. **Single-user** — no authentication/login. Opens straight to Dashboard.
2. **No external notifications** — in-app dashboard alerts only (overdue banner).
3. **SQLite for portability** — single file backup; zero config.
4. **Mobile-friendly** — responsive layout via CSS media queries.
5. **Color-coded badges** — Red/Green/Yellow/Blue for status/priority (novice-friendly).
6. **JSON for semi-structured data** — Sunday Recap notes and Plan assignments stored as JSON text columns.

## Architecture

```
chms/
├── app.py              # Flask application (all routes, ~480 lines)
├── models.py           # SQLite schema init + all query functions (~380 lines)
├── chms.db             # SQLite database (auto-created on first import)
├── static/
│   └── style.css       # All styles (~420 lines)
├── templates/          # 12 Jinja2 templates
│   ├── base.html       # Layout: header, nav, flash messages, footer
│   ├── dashboard.html  # Summary cards + overdue alert + recent tasks
│   ├── tasks.html      # Task board with filter bar
│   ├── task_form.html  # Task create/edit + follow-up notes
│   ├── members.html    # Member directory list
│   ├── member_form.html# Member add/edit form
│   ├── ministries.html # Ministry list
│   ├── ministry_form.html # Ministry add/edit form
│   ├── calendar.html   # Month grid + side panel
│   ├── event_form.html # Event add/edit form
│   ├── sunday_recap.html       # Recap list
│   ├── sunday_recap_form.html  # New recap form
│   ├── sunday_plan.html        # Plan list
│   └── sunday_plan_form.html   # New plan form
├── context.md          # This file
└── todo.md             # Task tracker
```

## Database Schema (7 tables)

```sql
-- Core tables (models.py:init_db)
members
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  name          TEXT NOT NULL
  role          TEXT DEFAULT ''
  phone         TEXT DEFAULT ''
  email         TEXT DEFAULT ''
  created_at    TEXT DEFAULT datetime('now')

ministries
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  name          TEXT NOT NULL UNIQUE
  description   TEXT DEFAULT ''
  created_at    TEXT DEFAULT datetime('now')

tasks
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  title         TEXT NOT NULL
  description   TEXT DEFAULT ''
  ministry_id   INTEGER REFERENCES ministries(id)
  member_id     INTEGER REFERENCES members(id)
  status        TEXT DEFAULT 'open'  -- open|in_progress|completed|blocked
  priority      TEXT DEFAULT 'medium' -- low|medium|high|critical
  due_date      TEXT (ISO date)
  created_at    TEXT DEFAULT datetime('now')
  completed_at  TEXT

task_updates
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  task_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE
  note          TEXT NOT NULL
  created_at    TEXT DEFAULT datetime('now')

events
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  title         TEXT NOT NULL
  event_type    TEXT DEFAULT 'meeting' -- service|program|meeting|special
  start_date    TEXT NOT NULL (ISO date)
  notes         TEXT DEFAULT ''
  created_at    TEXT DEFAULT datetime('now')

-- Sunday workflow tables (also in init_db)
sunday_recap
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  service_date  TEXT NOT NULL
  notes_json    TEXT DEFAULT '{}'  -- JSON dict: {"coordinators":"...", "ushers":"...", etc.}
  general_notes TEXT DEFAULT ''
  created_at    TEXT DEFAULT datetime('now')

sunday_plan
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  service_date  TEXT NOT NULL
  assignments_json TEXT DEFAULT '{}'  -- JSON dict: {"coordinators":"...", "ushers":"...", etc.}
  created_at    TEXT DEFAULT datetime('now')
```

## Route Map (app.py)

| Method | Route | Module | Description |
|--------|-------|--------|-------------|
| GET | `/` | Dashboard | Summary cards, overdue alert, recent tasks, upcoming events |
| GET | `/tasks` | Tasks | Task board with status/priority/ministry/member filters |
| GET/POST | `/tasks/add` | Tasks | Create new task |
| GET/POST | `/tasks/<id>` | Tasks | Task detail + edit + follow-up notes |
| POST | `/tasks/<id>/status` | Tasks | Quick status change |
| POST | `/tasks/<id>/delete` | Tasks | Delete task |
| GET | `/members` | Directory | Member list |
| GET/POST | `/members/add` | Directory | Add member |
| GET/POST | `/members/<id>/edit` | Directory | Edit member |
| POST | `/members/<id>/delete` | Directory | Delete member |
| GET | `/ministries` | Ministries | Ministry list |
| GET/POST | `/ministries/add` | Ministries | Add ministry |
| GET/POST | `/ministries/<id>/edit` | Ministries | Edit ministry |
| POST | `/ministries/<id>/delete` | Ministries | Delete ministry |
| GET | `/calendar` | Calendar | Month grid view + side panel |
| GET/POST | `/events/add` | Calendar | Add event |
| GET/POST | `/events/<id>/edit` | Calendar | Edit event |
| POST | `/events/<id>/delete` | Calendar | Delete event |
| GET | `/sunday/recap` | Sunday | Recap list |
| GET/POST | `/sunday/recap/add` | Sunday | New recap |
| GET | `/sunday/plan` | Sunday | Plan list |
| GET/POST | `/sunday/plan/add` | Sunday | New plan |

## Code Conventions

### models.py
- Every function opens and closes its own connection (no shared connection)
- All functions return `list[dict]` or `dict | None`
- `get_conn()` returns `sqlite3.Row`-based connections with WAL mode + foreign keys
- `init_db()` is idempotent (uses `CREATE TABLE IF NOT EXISTS`)
- The `init_db()` call at file bottom auto-creates tables on import

### app.py
- Template globals: `today()`, `status_badge_class()`, `priority_badge_class()`
- Flash messages with categories: `"success"` (green) and `"error"` (red)
- Sunday data (notes_json, assignments_json) stored as JSON text, parsed with `json.loads()` before template render
- `if __name__ == "__main__":` block: calls `init_db()`, opens browser, starts Flask

### Templates (Jinja2)
- All extend `base.html`
- `base.html`: header with nav links, flash message block, content block, footer
- CSS classes: `.btn`, `.btn-primary/outline/red/blue/purple/green/gray`, `.badge`, `.badge-open/progress/done/blocked/low/med/high/critical`
- Form pattern: `.form-card` with `.form-group` > `label + input/select/textarea`, `.form-row` for grid, `.form-actions` for buttons

## Known Limitations & Technical Debt

1. **Sunday JSON fields** — `notes_json` and `assignments_json` are stored as JSON text with no schema validation. If a key name changes, old data is invisible.
2. **No delete confirmation** on Sunday recap/plan items (should add modal or confirm dialog).
3. **No pagination** — task list could become slow with 1000+ tasks.
4. **No export/report** — no PDF or Excel export for committee records.
5. **Single-user only** — adding login would require session management and user table.
6. **No data migration** — the original Excel data must be manually re-entered.
7. **Static Sunday items** — `SUNDAY_ITEMS` and `PLAN_ROLES` are hardcoded lists in app.py. Should be database-driven for flexibility.
8. **No task deletion cascade** — deleting a member or ministry referenced by a task will leave orphaned foreign keys (the reference becomes null since `ON DELETE SET NULL` is not used).

## Setup & Run

```bash
# Requirements
pip install flask

# Run
cd /home/erangadesaram/Documents/Eranga/Docs/CHMS/chms
python3 app.py

# Opens at http://127.0.0.1:5000
# Database auto-created at chms/chms.db
```

## Future Enhancement Ideas

1. **Multi-user with login** — add `users` table, session auth, role-based access (admin/editor/viewer).
2. **Report generation** — use reportlab to generate PDF summaries of tasks, Sunday reports, monthly calendars.
3. **Excel import** — allow importing the old `Planning committe.xlsx` to seed initial data.
4. **Email digests** — weekly email to committee with overdue tasks and upcoming Sunday plan.
5. **Drag-and-drop task board** — Kanban-style column view.
6. **Recurring events** — ability to set events that repeat weekly/monthly/yearly.
7. **File attachments** — attach photos/PDFs to tasks and events.
8. **Audit log** — track who changed what and when (mainly useful when multi-user added).
9. **Theme settings** — editable church name, logo upload.
10. **Docker deployment** — Dockerfile + docker-compose for production hosting.
