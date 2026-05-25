# ChMS(prototype) Implementation Todo

## Legend
- `[x]` = completed
- `[ ]` = pending/not started
- Items grouped by priority: **P0** (critical) → **P3** (nice-to-have)

---

## ✅ Completed (All Phases 1-4)

### Phase 1 — Core (Task Board + Directory)
- [x] 1.1 Create project structure (app.py, directories, context.md, todo.md)
- [x] 1.2 Implement SQLite schema (models.py with 7 tables)
- [x] 1.3 Create base.html template (header nav, flash messages, footer)
- [x] 1.4 Create static/style.css (responsive, badge system, card grid)
- [x] 1.5 Implement Directory module (list, add, edit, delete members)
- [x] 1.6 Implement Ministries module (list, add, edit, delete)
- [x] 1.7 Implement Task Board with status/priority/ministry/member filters
- [x] 1.8 Implement Task Create/Edit form with all fields
- [x] 1.9 Implement Task inline status update
- [x] 1.10 Implement Task follow-up notes (task_updates table + comment UI)
- [x] 1.11 Seed sample data and verify all CRUD paths

### Phase 2 — Calendar
- [x] 2.1 Implement Event CRUD with date picker (4 event types)
- [x] 2.2 Implement Calendar month grid with event dots + side panel

### Phase 3 — Sunday Workflow
- [x] 3.1 Implement Sunday Recap (date + per-item notes + general notes)
- [x] 3.2 Implement Sunday Plan (date + role-by-role assignments)
- [x] 3.3 Workflow: Recap records past services; Plan prepares future services

### Phase 4 — Dashboard & Polish
- [x] 4.1 Dashboard: summary cards (total/open/in-progress/completed/overdue)
- [x] 4.2 Dashboard: overdue alert banner (red, links to task list)
- [x] 4.3 Dashboard: recent tasks table + upcoming events + next Sunday widget
- [x] 4.4 Final comprehensive testing (all GET + POST routes verified)

---

## 📋 P0 — Must Have (Bugs/Completeness)

- [ ] **1. Add delete confirmation modals** — Currently only `confirm()` JS dialogs for task/member/ministry/event delete. Replace with proper modal or at minimum ensure all destructive actions have confirmation.
- [ ] **2. Add pagination to task list** — `get_tasks()` fetches all rows. Add `LIMIT ? OFFSET ?` with page controls when tasks exceed 100.
- [ ] **3. Handle orphaned references on delete** — When a member or ministry is deleted, tasks referencing them get `NULL`. Either add `ON DELETE SET NULL` or warn user about affected tasks before delete.
- [ ] **4. Validate Sunday JSON fields** — Add try/except around `json.loads()` in templates (currently done in routes, but templates also access `.get()` on the parsed dict — verify all paths).
- [ ] **5. Add CSS print styles** — For printing calendar and task lists.

---

## 📋 P1 — Should Have (Important Enhancements)

- [ ] **6. Make Sunday items/roles database-driven**
  - Currently `SUNDAY_ITEMS` and `PLAN_ROLES` are hardcoded lists in `app.py`
  - Create a `sunday_config` table with `module` (recap/plan), `item_name`, `sort_order`
  - Load dynamically in routes and templates
  - Allows committee to customize items without code changes

- [ ] **7. Add export/print for Sunday Recap and Plan**
  - "Print" button that opens a printer-friendly view of a specific Sunday
  - Bonus: PDF export using reportlab (already in requirements)

- [ ] **8. Add event recurrence**
  - Weekly, monthly, yearly repeat options
  - Store repeat rule in events table (e.g., `repeat: "weekly"`)
  - Generate instances on the fly in calendar view

- [ ] **9. Add task due-date reminders on dashboard**
  - "Due today" section (separate from overdue)
  - "Due this week" section
  - Color-coded by urgency

- [ ] **10. Add search bar to task board**
  - Currently only filters (dropdowns). Add a text search for title/description.

---

## 📋 P2 — Nice to Have (Future Features)

- [ ] **11. Multi-user support**
  - Add `users` table with hashed passwords
  - Add login/logout with Flask sessions
  - Roles: admin (full), editor (CRUD), viewer (read-only)
  - Member/task audit trail (`updated_by` fields)

- [ ] **12. Excel/CSV import for initial data**
  - Upload old `Planning committe.xlsx`
  - Parse known sheets and insert into corresponding tables
  - Map columns to schema fields

- [ ] **13. Data export (Excel/CSV)**
  - Export tasks, members, events as CSV or XLSX
  - Export Sunday recap as PDF report

- [ ] **14. Dashboard chart/graph**
  - Simple bar chart: tasks by status
  - Calendar heatmap: events per month
  - Use Chart.js (lightweight, CDN-loaded)

- [ ] **15. Task duplicate / template feature**
  - "Duplicate task" button for recurring tasks
  - Task templates for common recurring items

---

## 📋 P3 — Polish & Tech Debt

- [ ] **16. Add proper NOT FOUND (404) pages**
  - Currently missing routes for `/tasks/9999` etc. throw 500 instead of 404

- [ ] **17. Loading states for slow operations**
  - Not critical for SQLite (fast), but good practice

- [ ] **18. Keyboard shortcuts**
  - `n` = new task, `c` = calendar, `d` = dashboard
  - Useful for fast data entry

- [ ] **19. Dark mode toggle**
  - CSS custom properties for theme switching

- [ ] **20. i18n / English only is fine** — No change needed; document that UI is English-only

- [ ] **21. Write unit tests**
  - Test models.py CRUD functions
  - Test app.py routes with Flask test client
  - Test template rendering with sample data

- [ ] **22. Dockerize**
  - Dockerfile: Python 3.10 slim + Flask
  - docker-compose.yml for easy startup
  - Volume mount for persistent DB

---

## 🐛 Known Bugs

- (None reported yet — all routes return 200 in integration tests)

## 📝 Notes for Future Developer

### How data flows
1. `models.py:init_db()` auto-runs on import → creates all 7 tables
2. `app.py` imports all functions from `models.py`
3. Each route opens a connection, queries, closes
4. Sunday JSON: stored as `json.dumps(dict)` in DB, loaded with `json.loads()` on read
5. Dashboard computes counts by calling `get_task_count(status)` and `get_overdue_count()` separately

### Where to add a new feature
- **New DB table** → add `CREATE TABLE` to `init_db()` in `models.py`
- **New query function** → add to `models.py`, export at top
- **New route** → add to `app.py` with `@app.route`
- **New template** → create in `templates/`, extend `base.html`
- **New CSS** → add classes to `static/style.css`

### Testing approach
```bash
cd /home/erangadesaram/Documents/Eranga/Docs/CHMS/chms
rm -f chms.db  # Reset database
python3 -c "
import os; os.environ['WERKZEUG_RUN_MAIN'] = 'true'
from app import app
with app.test_client() as c:
    r = c.get('/')
    print(f'Dashboard: {r.status_code}')
    # ... test more routes
"
```

### Project location
- `/home/erangadesaram/Documents/Eranga/Docs/CHMS/chms/`
- Sibling to `lwc-salary-system/` (reference app for styling)
- Source Excel: `../Planning committe.xlsx`
