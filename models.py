import sqlite3
import os
from datetime import date, datetime, timedelta
from calendar import monthcalendar

DB_PATH = os.environ.get("CHMS_DB_PATH") or os.path.join(os.path.dirname(__file__), "chms.db")

TASK_STATUSES = ["open", "in_progress", "completed", "on_hold", "suspended"]
TASK_PRIORITIES = ["low", "medium", "high", "critical"]
RECURRING_TYPES = ["none", "weekly", "bi_weekly", "monthly", "quarterly", "annual"]
TYPE_FLAGS = ["Program", "Meeting", "Event", "Service"]
PRIORITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

STATUS_CASCADE_ORDER = [
    "on_hold",
    "suspended",
    "in_progress",
    "open",
    "completed",
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            designation TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS program_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sub_programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_category_id INTEGER NOT NULL REFERENCES program_categories(id),
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            in_charge_id INTEGER REFERENCES members(id),
            recurring_type TEXT NOT NULL DEFAULT 'none'
                CHECK(recurring_type IN ('none','weekly','bi_weekly','monthly','quarterly','annual')),
            add_to_calendar INTEGER NOT NULL DEFAULT 0,
            type_flag TEXT NOT NULL DEFAULT 'Program'
                CHECK(type_flag IN ('Program','Meeting','Event','Service')),
            notes TEXT NOT NULL DEFAULT '',
            parent_id INTEGER REFERENCES sub_programs(id),
            generation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sub_program_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_program_id INTEGER NOT NULL REFERENCES sub_programs(id) ON DELETE CASCADE,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            UNIQUE(sub_program_id, member_id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_program_id INTEGER NOT NULL REFERENCES sub_programs(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            due_date TEXT,
            assigned_to INTEGER REFERENCES members(id),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open','in_progress','completed','on_hold','suspended')),
            priority TEXT NOT NULL DEFAULT 'medium'
                CHECK(priority IN ('low','medium','high','critical')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS task_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            sub_program_id INTEGER REFERENCES sub_programs(id),
            recurring_type TEXT NOT NULL DEFAULT 'none'
                CHECK(recurring_type IN ('none','weekly','bi_weekly','monthly','quarterly','annual')),
            type_flag TEXT NOT NULL DEFAULT 'Event'
                CHECK(type_flag IN ('Program','Meeting','Event','Service')),
            start_date TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_sub_program ON tasks(sub_program_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to);
        CREATE INDEX IF NOT EXISTS idx_sub_programs_category ON sub_programs(program_category_id);
        CREATE INDEX IF NOT EXISTS idx_sub_programs_due ON sub_programs(due_date);
        CREATE INDEX IF NOT EXISTS idx_sub_programs_parent ON sub_programs(parent_id);
        CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date);
    """)
    conn.commit()
    conn.close()


# ─── Members ──────────────────────────────────────────────

def get_members():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_member(member_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM members WHERE id=?", (member_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_member(name, designation, phone, email):
    conn = get_conn()
    conn.execute(
        "INSERT INTO members (name, designation, phone, email) VALUES (?,?,?,?)",
        (name.strip(), designation.strip(), phone.strip(), email.strip()),
    )
    conn.commit()
    mid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return mid


def update_member(member_id, name, designation, phone, email):
    conn = get_conn()
    conn.execute(
        "UPDATE members SET name=?, designation=?, phone=?, email=? WHERE id=?",
        (name.strip(), designation.strip(), phone.strip(), email.strip(), member_id),
    )
    conn.commit()
    conn.close()


def delete_member(member_id):
    conn = get_conn()
    conn.execute("DELETE FROM members WHERE id=?", (member_id,))
    conn.commit()
    conn.close()


# ─── Program Categories ──────────────────────────────────

def get_program_categories():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM program_categories ORDER BY sort_order, name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_program_category(category_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM program_categories WHERE id=?", (category_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_program_category(name, description, sort_order=0):
    conn = get_conn()
    conn.execute(
        "INSERT INTO program_categories (name, description, sort_order) VALUES (?,?,?)",
        (name.strip(), description.strip(), sort_order),
    )
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return cid


def update_program_category(category_id, name, description, sort_order):
    conn = get_conn()
    conn.execute(
        "UPDATE program_categories SET name=?, description=?, sort_order=? WHERE id=?",
        (name.strip(), description.strip(), sort_order, category_id),
    )
    conn.commit()
    conn.close()


def delete_program_category(category_id):
    conn = get_conn()
    conn.execute("DELETE FROM program_categories WHERE id=?", (category_id,))
    conn.commit()
    conn.close()


# ─── Sub Programs ────────────────────────────────────────

def get_sub_programs(category_id=None, status_filter=None, active_only=False, search=None):
    conn = get_conn()
    sql = """
        SELECT sp.*, 
               pc.name AS category_name,
               m.name AS in_charge_name
        FROM sub_programs sp
        LEFT JOIN program_categories pc ON sp.program_category_id = pc.id
        LEFT JOIN members m ON sp.in_charge_id = m.id
        WHERE 1=1
    """
    params = []
    if category_id:
        sql += " AND sp.program_category_id=?"
        params.append(category_id)
    if active_only:
        sql += " AND sp.due_date >= date('now')"
    if search:
        sql += " AND (sp.title LIKE ? OR sp.description LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
    sql += " ORDER BY sp.created_at DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sub_program(sub_program_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT sp.*, 
               pc.name AS category_name,
               m.name AS in_charge_name
        FROM sub_programs sp
        LEFT JOIN program_categories pc ON sp.program_category_id = pc.id
        LEFT JOIN members m ON sp.in_charge_id = m.id
        WHERE sp.id=?
    """, (sub_program_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_sub_program(category_id, title, description, due_date, in_charge_id,
                    recurring_type, add_to_calendar, type_flag, notes, parent_id=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO sub_programs 
            (program_category_id, title, description, due_date, in_charge_id,
             recurring_type, add_to_calendar, type_flag, notes, parent_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (category_id, title.strip(), description.strip(), due_date or None,
          in_charge_id or None, recurring_type, 1 if add_to_calendar else 0,
          type_flag, notes.strip(), parent_id))
    conn.commit()
    sub_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return sub_id


def update_sub_program(sub_id, category_id, title, description, due_date,
                       in_charge_id, recurring_type, add_to_calendar, type_flag, notes):
    conn = get_conn()
    conn.execute("""
        UPDATE sub_programs SET
            program_category_id=?, title=?, description=?, due_date=?,
            in_charge_id=?, recurring_type=?, add_to_calendar=?, 
            type_flag=?, notes=?, updated_at=datetime('now')
        WHERE id=?
    """, (category_id, title.strip(), description.strip(), due_date or None,
          in_charge_id or None, recurring_type, 1 if add_to_calendar else 0,
          type_flag, notes.strip(), sub_id))
    conn.commit()
    conn.close()


def delete_sub_program(sub_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT COUNT(*) AS c FROM tasks 
        WHERE sub_program_id=? AND status IN ('open','in_progress')
    """, (sub_id,)).fetchone()
    if row["c"] > 0:
        conn.close()
        return False
    conn.execute("DELETE FROM sub_programs WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()
    return True


# ─── Sub Program Members ─────────────────────────────────

def get_sub_program_members(sub_program_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT m.id, m.name, m.designation
        FROM sub_program_members spm
        JOIN members m ON spm.member_id = m.id
        WHERE spm.sub_program_id=?
        ORDER BY m.name
    """, (sub_program_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_sub_program_member(sub_program_id, member_id):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO sub_program_members (sub_program_id, member_id) VALUES (?,?)",
            (sub_program_id, member_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()


def remove_sub_program_member(sub_program_id, member_id):
    conn = get_conn()
    conn.execute(
        "DELETE FROM sub_program_members WHERE sub_program_id=? AND member_id=?",
        (sub_program_id, member_id),
    )
    conn.commit()
    conn.close()


# ─── Derived Status / Priority ──────────────────────────

def _get_tasks_for_sub_program(sub_program_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT status, priority FROM tasks WHERE sub_program_id=?",
        (sub_program_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_status(tasks):
    if not tasks:
        return "open"
    seen = set(t["status"] for t in tasks)
    # Partial completion = in_progress
    if "completed" in seen and len(seen) > 1:
        seen.add("in_progress")
    for s in STATUS_CASCADE_ORDER:
        if s in seen:
            return s
    return "open"


def compute_priority(tasks, status_filter=("open", "in_progress")):
    relevant = [t for t in tasks if t["status"] in status_filter]
    if not relevant:
        return None
    best = max(relevant, key=lambda t: PRIORITY_ORDER.get(t["priority"], 0))
    return best["priority"]


def get_sub_program_derived(sub_program_id):
    tasks = _get_tasks_for_sub_program(sub_program_id)
    return {
        "status": compute_status(tasks),
        "priority": compute_priority(tasks),
        "task_count": len(tasks),
    }


def get_all_sub_programs_with_status(category_id=None, search=None):
    sub_programs = get_sub_programs(category_id=category_id, search=search)
    for sp in sub_programs:
        derived = get_sub_program_derived(sp["id"])
        sp["derived_status"] = derived["status"]
        sp["derived_priority"] = derived["priority"]
        sp["task_count"] = derived["task_count"]
    return sub_programs


def get_sub_program_counts():
    today_iso = date.today().isoformat()
    all_subs = get_sub_programs()
    counts = {"total": len(all_subs), "open": 0, "in_progress": 0,
              "completed": 0, "on_hold_suspended": 0, "overdue": 0}
    for sp in all_subs:
        tasks = _get_tasks_for_sub_program(sp["id"])
        status = compute_status(tasks)
        if status == "completed":
            counts["completed"] += 1
        elif status == "on_hold" or status == "suspended":
            counts["on_hold_suspended"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
        else:
            counts["open"] += 1
        # overdue: not completed/on_hold/suspended AND past due
        if status not in ("completed", "on_hold", "suspended"):
            if sp["due_date"] and sp["due_date"] < today_iso:
                counts["overdue"] += 1
    return counts


# ─── Overdue / Active Sub-Programs ──────────────────────

def get_overdue_sub_programs():
    today_iso = date.today().isoformat()
    all_subs = get_sub_programs()
    result = []
    for sp in all_subs:
        tasks = _get_tasks_for_sub_program(sp["id"])
        status = compute_status(tasks)
        if status in ("completed", "on_hold", "suspended"):
            continue
        if sp["due_date"] and sp["due_date"] < today_iso:
            sp["derived_status"] = status
            sp["derived_priority"] = compute_priority(tasks)
            sp["task_count"] = len(tasks)
            result.append(sp)
    result.sort(key=lambda x: x.get("due_date") or "")
    return result


def get_active_sub_programs(search=None):
    all_subs = get_sub_programs(search=search)
    result = []
    for sp in all_subs:
        tasks = _get_tasks_for_sub_program(sp["id"])
        status = compute_status(tasks)
        if status == "completed":
            continue
        sp["derived_status"] = status
        sp["derived_priority"] = compute_priority(tasks)
        sp["task_count"] = len(tasks)
        result.append(sp)
    result.sort(key=lambda x: x.get("due_date") or "")
    return result


# ─── Tasks ───────────────────────────────────────────────

def get_tasks(sub_program_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.*, m.name AS assigned_name
        FROM tasks t
        LEFT JOIN members m ON t.assigned_to = m.id
        WHERE t.sub_program_id=?
        ORDER BY t.created_at DESC
    """, (sub_program_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_task(task_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT t.*, m.name AS assigned_name, sp.title AS sub_program_title,
               sp.due_date AS sp_due_date
        FROM tasks t
        LEFT JOIN members m ON t.assigned_to = m.id
        LEFT JOIN sub_programs sp ON t.sub_program_id = sp.id
        WHERE t.id=?
    """, (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_task(sub_program_id, title, due_date, assigned_to, priority):
    conn = get_conn()
    conn.execute("""
        INSERT INTO tasks (sub_program_id, title, due_date, assigned_to, priority)
        VALUES (?,?,?,?,?)
    """, (sub_program_id, title.strip(), due_date or None,
          assigned_to or None, priority))
    conn.commit()
    tid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return tid


def update_task(task_id, title, due_date, assigned_to, priority, status):
    conn = get_conn()
    completed_at = datetime.now().isoformat() if status == "completed" else None
    conn.execute("""
        UPDATE tasks SET title=?, due_date=?, assigned_to=?, priority=?, 
               status=?, completed_at=? WHERE id=?
    """, (title.strip(), due_date or None, assigned_to or None,
          priority, status, completed_at, task_id))
    conn.commit()
    conn.close()


def update_task_status(task_id, status):
    conn = get_conn()
    completed_at = datetime.now().isoformat() if status == "completed" else None
    conn.execute(
        "UPDATE tasks SET status=?, completed_at=? WHERE id=?",
        (status, completed_at, task_id),
    )
    conn.commit()
    conn.close()


def delete_task(task_id):
    conn = get_conn()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


# ─── Task Updates ────────────────────────────────────────

def get_task_updates(task_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_updates WHERE task_id=? ORDER BY created_at DESC",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_task_update(task_id, note):
    conn = get_conn()
    conn.execute(
        "INSERT INTO task_updates (task_id, note) VALUES (?,?)",
        (task_id, note.strip()),
    )
    conn.commit()
    conn.close()


# ─── Events ──────────────────────────────────────────────

def get_events(year=None, month=None):
    conn = get_conn()
    sql = """SELECT e.*, sp.title AS sub_program_title
             FROM events e
             LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
             WHERE 1=1"""
    params = []
    if year and month:
        sql += " AND strftime('%Y', e.start_date)=? AND strftime('%m', e.start_date)=?"
        params.append(str(year))
        params.append(f"{int(month):02d}")
    sql += " ORDER BY e.start_date"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_event(event_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT e.*, sp.title AS sub_program_title
        FROM events e
        LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
        WHERE e.id=?
    """, (event_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_event(title, sub_program_id, recurring_type, type_flag, start_date, notes):
    conn = get_conn()
    conn.execute("""
        INSERT INTO events (title, sub_program_id, recurring_type, type_flag, start_date, notes)
        VALUES (?,?,?,?,?,?)
    """, (title.strip(), sub_program_id or None, recurring_type,
          type_flag, start_date, notes.strip()))
    conn.commit()
    event_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.close()
    return event_id


def update_event(event_id, title, sub_program_id, recurring_type, type_flag,
                 start_date, notes):
    conn = get_conn()
    conn.execute("""
        UPDATE events SET title=?, sub_program_id=?, recurring_type=?, type_flag=?,
               start_date=?, notes=? WHERE id=?
    """, (title.strip(), sub_program_id or None, recurring_type,
          type_flag, start_date, notes.strip(), event_id))
    conn.commit()
    conn.close()


def delete_event(event_id):
    conn = get_conn()
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()


def get_upcoming_schedule(limit=20):
    today_iso = date.today().isoformat()
    schedule = []

    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, due_date AS event_date, type_flag, 'sub_program' AS source
        FROM sub_programs
        WHERE add_to_calendar=1 AND due_date >= ?
        ORDER BY due_date
        LIMIT ?
    """, (today_iso, limit)).fetchall()
    schedule.extend(dict(r) for r in rows)

    rows = conn.execute("""
        SELECT id, title, start_date AS event_date, type_flag, 'event' AS source
        FROM events
        WHERE start_date >= ?
        ORDER BY start_date
        LIMIT ?
    """, (today_iso, limit)).fetchall()
    schedule.extend(dict(r) for r in rows)
    conn.close()

    schedule.sort(key=lambda x: x["event_date"])
    return schedule[:limit]


# ─── Calendar Data ────────────────────────────────────────

def get_calendar_entries(year, month):
    month_start = f"{year:04d}-{month:02d}"
    entries = []

    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, type_flag, due_date AS start_date, 'sub_program' AS source
        FROM sub_programs
        WHERE add_to_calendar=1 AND strftime('%Y-%m', due_date)=?
        ORDER BY due_date
    """, (month_start,)).fetchall()
    entries.extend(dict(r) for r in rows)

    rows = conn.execute("""
        SELECT id, title, type_flag, start_date, 'event' AS source
        FROM events
        WHERE strftime('%Y-%m', start_date)=?
        ORDER BY start_date
    """, (month_start,)).fetchall()
    entries.extend(dict(r) for r in rows)
    conn.close()

    return entries


# ─── Recurrence ──────────────────────────────────────────

RECURRENCE_DELTA = {
    "weekly": timedelta(days=7),
    "bi_weekly": timedelta(days=14),
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=91),
    "annual": timedelta(days=365),
}


def get_config(key, default=None):
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM app_config WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO app_config (key, value) VALUES (?,?)",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def generate_recurring_instances():
    last_check = get_config("last_recurrence_check", "2000-01-01")
    today_dt = date.today()
    today_iso = today_dt.isoformat()
    cutoff = (today_dt + timedelta(days=7)).isoformat()

    if last_check >= today_iso:
        return 0

    created = 0
    conn = get_conn()

    base_subs = conn.execute("""
        SELECT * FROM sub_programs 
        WHERE recurring_type != 'none' AND parent_id IS NULL
    """).fetchall()

    for base in base_subs:
        base = dict(base)
        delta = RECURRENCE_DELTA.get(base["recurring_type"])
        if not delta:
            continue
        original_date = datetime.strptime(base["due_date"], "%Y-%m-%d").date()
        gen = 1

        while True:
            next_date = original_date + delta * gen
            if next_date > today_dt + timedelta(days=7):
                break
            if next_date < today_dt:
                gen += 1
                continue

            next_iso = next_date.isoformat()

            existing = conn.execute(
                "SELECT id FROM sub_programs WHERE parent_id=? AND generation=?",
                (base["id"], gen),
            ).fetchone()
            if existing:
                gen += 1
                continue

            conn.execute("""
                INSERT INTO sub_programs 
                    (program_category_id, title, description, due_date, in_charge_id,
                     recurring_type, add_to_calendar, type_flag, notes, parent_id, generation)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                base["program_category_id"], base["title"], base["description"],
                next_iso, base["in_charge_id"], base["recurring_type"],
                base["add_to_calendar"], base["type_flag"], base["notes"],
                base["id"], gen,
            ))
            new_sp_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

            # Copy members
            member_rows = conn.execute(
                "SELECT member_id FROM sub_program_members WHERE sub_program_id=?",
                (base["id"],),
            ).fetchall()
            for mr in member_rows:
                conn.execute(
                    "INSERT INTO sub_program_members (sub_program_id, member_id) VALUES (?,?)",
                    (new_sp_id, mr["member_id"]),
                )

            # Copy tasks with shifted dates
            task_rows = conn.execute(
                "SELECT * FROM tasks WHERE sub_program_id=?", (base["id"],)
            ).fetchall()
            for tr in task_rows:
                tr = dict(tr)
                task_due = None
                if tr["due_date"]:
                    td = datetime.strptime(tr["due_date"], "%Y-%m-%d").date()
                    offset = (td - original_date).days
                    task_due = (next_date + timedelta(days=offset)).isoformat()
                conn.execute("""
                    INSERT INTO tasks (sub_program_id, title, due_date, assigned_to, priority, status)
                    VALUES (?,?,?,?,?,?)
                """, (new_sp_id, tr["title"], task_due, tr["assigned_to"],
                      tr["priority"], "open"))

            # Calendar entry if needed
            if base["add_to_calendar"]:
                conn.execute("""
                    INSERT INTO events (title, sub_program_id, type_flag, start_date, recurring_type, notes)
                    VALUES (?,?,?,?,?,?)
                """, (base["title"], new_sp_id, base["type_flag"], next_iso,
                      base["recurring_type"], ""))

            created += 1
            gen += 1

    conn.commit()
    conn.close()
    if created:
        set_config("last_recurrence_check", today_iso)
    return created


# ─── Auto-init ────────────────────────────────────────────

init_db()
