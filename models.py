import os
import psycopg2
import psycopg2.extras
from datetime import date, datetime, timedelta

DATABASE_URL = os.environ["DATABASE_URL"]

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


class _Connection:
    """Wraps a psycopg2 connection with an execute() method compatible
    with the old sqlite3.Connection.execute() API."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or ())
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn():
    return _Connection(psycopg2.connect(DATABASE_URL))


def init_db():
    conn = get_conn()
    tables = [
        """
        CREATE TABLE IF NOT EXISTS members (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            designation TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS program_categories (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sub_programs (
            id SERIAL PRIMARY KEY,
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
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
            updated_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sub_program_members (
            id SERIAL PRIMARY KEY,
            sub_program_id INTEGER NOT NULL REFERENCES sub_programs(id) ON DELETE CASCADE,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            UNIQUE(sub_program_id, member_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            sub_program_id INTEGER NOT NULL REFERENCES sub_programs(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            due_date TEXT,
            assigned_to INTEGER REFERENCES members(id),
            status TEXT NOT NULL DEFAULT 'open'
                CHECK(status IN ('open','in_progress','completed','on_hold','suspended')),
            priority TEXT NOT NULL DEFAULT 'medium'
                CHECK(priority IN ('low','medium','high','critical')),
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
            completed_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS task_updates (
            id SERIAL PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            note TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            sub_program_id INTEGER REFERENCES sub_programs(id),
            recurring_type TEXT NOT NULL DEFAULT 'none'
                CHECK(recurring_type IN ('none','weekly','bi_weekly','monthly','quarterly','annual')),
            type_flag TEXT NOT NULL DEFAULT 'Event'
                CHECK(type_flag IN ('Program','Meeting','Event','Service')),
            start_date TEXT NOT NULL,
            expiry_date TEXT,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer'
                CHECK(role IN ('admin','power_user','viewer')),
            display_name TEXT NOT NULL DEFAULT '',
            is_approved INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        )
        """,
    ]
    for ddl in tables:
        conn.execute(ddl)
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_tasks_sub_program ON tasks(sub_program_id)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks(assigned_to)",
        "CREATE INDEX IF NOT EXISTS idx_sub_programs_category ON sub_programs(program_category_id)",
        "CREATE INDEX IF NOT EXISTS idx_sub_programs_due ON sub_programs(due_date)",
        "CREATE INDEX IF NOT EXISTS idx_sub_programs_parent ON sub_programs(parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_events_date ON events(start_date)",
    ]
    for idx in indexes:
        conn.execute(idx)
    conn.execute("""
        DO $$ BEGIN
            ALTER TABLE events ADD COLUMN expiry_date TEXT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$;
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
    row = conn.execute("SELECT * FROM members WHERE id=%s", (member_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_member(name, designation, phone, email):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO members (name, designation, phone, email) VALUES (%s,%s,%s,%s) RETURNING id",
        (name.strip(), designation.strip(), phone.strip(), email.strip()),
    )
    mid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return mid


def update_member(member_id, name, designation, phone, email):
    conn = get_conn()
    conn.execute(
        "UPDATE members SET name=%s, designation=%s, phone=%s, email=%s WHERE id=%s",
        (name.strip(), designation.strip(), phone.strip(), email.strip(), member_id),
    )
    conn.commit()
    conn.close()


def delete_member(member_id):
    conn = get_conn()
    conn.execute("UPDATE sub_programs SET in_charge_id=NULL WHERE in_charge_id=%s", (member_id,))
    conn.execute("UPDATE tasks SET assigned_to=NULL WHERE assigned_to=%s", (member_id,))
    conn.execute("DELETE FROM members WHERE id=%s", (member_id,))
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
        "SELECT * FROM program_categories WHERE id=%s", (category_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_program_category(name, description, sort_order=0):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO program_categories (name, description, sort_order) VALUES (%s,%s,%s) RETURNING id",
        (name.strip(), description.strip(), sort_order),
    )
    cid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return cid


def update_program_category(category_id, name, description, sort_order):
    conn = get_conn()
    conn.execute(
        "UPDATE program_categories SET name=%s, description=%s, sort_order=%s WHERE id=%s",
        (name.strip(), description.strip(), sort_order, category_id),
    )
    conn.commit()
    conn.close()


def delete_program_category(category_id):
    conn = get_conn()
    conn.execute("UPDATE sub_programs SET program_category_id=NULL WHERE program_category_id=%s", (category_id,))
    conn.execute("DELETE FROM program_categories WHERE id=%s", (category_id,))
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
        sql += " AND sp.program_category_id=%s"
        params.append(category_id)
    if active_only:
        sql += " AND sp.due_date >= CURRENT_DATE::TEXT"
    if search:
        sql += " AND (sp.title LIKE %s OR sp.description LIKE %s)"
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
        WHERE sp.id=%s
    """, (sub_program_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_sub_program(category_id, title, description, due_date, in_charge_id,
                    recurring_type, add_to_calendar, type_flag, notes, parent_id=None):
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO sub_programs 
            (program_category_id, title, description, due_date, in_charge_id,
             recurring_type, add_to_calendar, type_flag, notes, parent_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
    """, (category_id, title.strip(), description.strip(), due_date or None,
          in_charge_id or None, recurring_type, 1 if add_to_calendar else 0,
          type_flag, notes.strip(), parent_id))
    sub_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return sub_id


def update_sub_program(sub_id, category_id, title, description, due_date,
                       in_charge_id, recurring_type, add_to_calendar, type_flag, notes):
    conn = get_conn()
    conn.execute("""
        UPDATE sub_programs SET
            program_category_id=%s, title=%s, description=%s, due_date=%s,
            in_charge_id=%s, recurring_type=%s, add_to_calendar=%s, 
            type_flag=%s, notes=%s, updated_at=TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')
        WHERE id=%s
    """, (category_id, title.strip(), description.strip(), due_date or None,
          in_charge_id or None, recurring_type, 1 if add_to_calendar else 0,
          type_flag, notes.strip(), sub_id))
    conn.commit()
    conn.close()


def delete_sub_program(sub_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT COUNT(*) AS c FROM tasks 
        WHERE sub_program_id=%s AND status IN ('open','in_progress')
    """, (sub_id,)).fetchone()
    if row["c"] > 0:
        conn.close()
        return False
    conn.execute("UPDATE events SET sub_program_id=NULL WHERE sub_program_id IN (SELECT id FROM sub_programs WHERE parent_id=%s)", (sub_id,))
    conn.execute("DELETE FROM sub_programs WHERE parent_id=%s", (sub_id,))
    conn.execute("UPDATE events SET sub_program_id=NULL WHERE sub_program_id=%s", (sub_id,))
    conn.execute("DELETE FROM sub_programs WHERE id=%s", (sub_id,))
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
        WHERE spm.sub_program_id=%s
        ORDER BY m.name
    """, (sub_program_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_sub_program_member(sub_program_id, member_id):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sub_program_members (sub_program_id, member_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            (sub_program_id, member_id),
        )
        conn.commit()
    except Exception:
        pass
    conn.close()


def remove_sub_program_member(sub_program_id, member_id):
    conn = get_conn()
    conn.execute(
        "DELETE FROM sub_program_members WHERE sub_program_id=%s AND member_id=%s",
        (sub_program_id, member_id),
    )
    conn.commit()
    conn.close()


# ─── Derived Status / Priority ──────────────────────────

def _get_tasks_for_sub_program(sub_program_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT status, priority FROM tasks WHERE sub_program_id=%s",
        (sub_program_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _get_tasks_batch(sub_program_ids):
    if not sub_program_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("%s" for _ in sub_program_ids)
    rows = conn.execute(
        f"SELECT sub_program_id, status, priority FROM tasks WHERE sub_program_id IN ({placeholders})",
        sub_program_ids,
    ).fetchall()
    conn.close()
    result = {sid: [] for sid in sub_program_ids}
    for r in rows:
        result[r["sub_program_id"]].append({"status": r["status"], "priority": r["priority"]})
    return result


def compute_status(tasks):
    if not tasks:
        return "open"
    seen = set(t["status"] for t in tasks)
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
    if not sub_programs:
        return []
    ids = [sp["id"] for sp in sub_programs]
    batch = _get_tasks_batch(ids)
    for sp in sub_programs:
        tasks = batch.get(sp["id"], [])
        sp["derived_status"] = compute_status(tasks)
        sp["derived_priority"] = compute_priority(tasks)
        sp["task_count"] = len(tasks)
    return sub_programs


def get_sub_program_counts():
    today_iso = date.today().isoformat()
    all_subs = get_sub_programs()
    counts = {"total": len(all_subs), "open": 0, "in_progress": 0,
              "completed": 0, "on_hold_suspended": 0, "overdue": 0}
    if not all_subs:
        return counts
    ids = [sp["id"] for sp in all_subs]
    batch = _get_tasks_batch(ids)
    for sp in all_subs:
        tasks = batch.get(sp["id"], [])
        status = compute_status(tasks)
        if status == "completed":
            counts["completed"] += 1
        elif status == "on_hold" or status == "suspended":
            counts["on_hold_suspended"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
        else:
            counts["open"] += 1
        if status not in ("completed", "on_hold", "suspended"):
            if sp["due_date"] and sp["due_date"] < today_iso:
                counts["overdue"] += 1
    return counts


# ─── Overdue / Active Sub-Programs ──────────────────────

def get_overdue_sub_programs():
    today_iso = date.today().isoformat()
    all_subs = get_sub_programs()
    if not all_subs:
        return []
    ids = [sp["id"] for sp in all_subs]
    batch = _get_tasks_batch(ids)
    result = []
    for sp in all_subs:
        tasks = batch.get(sp["id"], [])
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
    if not all_subs:
        return []
    ids = [sp["id"] for sp in all_subs]
    batch = _get_tasks_batch(ids)
    result = []
    for sp in all_subs:
        tasks = batch.get(sp["id"], [])
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

def get_tasks(sub_program_id, page=1, per_page=100):
    conn = get_conn()
    count_row = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE sub_program_id=%s",
        (sub_program_id,),
    ).fetchone()
    count = count_row["c"]
    offset = (page - 1) * per_page
    rows = conn.execute("""
        SELECT t.*, m.name AS assigned_name
        FROM tasks t
        LEFT JOIN members m ON t.assigned_to = m.id
        WHERE t.sub_program_id=%s
        ORDER BY t.created_at DESC
        LIMIT %s OFFSET %s
    """, (sub_program_id, per_page, offset)).fetchall()
    conn.close()
    return [dict(r) for r in rows], count


def get_task(task_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT t.*, m.name AS assigned_name, sp.title AS sub_program_title,
               sp.due_date AS sp_due_date
        FROM tasks t
        LEFT JOIN members m ON t.assigned_to = m.id
        LEFT JOIN sub_programs sp ON t.sub_program_id = sp.id
        WHERE t.id=%s
    """, (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_task(sub_program_id, title, due_date, assigned_to, priority):
    conn = get_conn()
    cur = conn.execute("""
        INSERT INTO tasks (sub_program_id, title, due_date, assigned_to, priority)
        VALUES (%s,%s,%s,%s,%s) RETURNING id
    """, (sub_program_id, title.strip(), due_date or None,
          assigned_to or None, priority))
    tid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return tid


def update_task(task_id, title, due_date, assigned_to, priority, status):
    conn = get_conn()
    completed_at = datetime.now().isoformat() if status == "completed" else None
    conn.execute("""
        UPDATE tasks SET title=%s, due_date=%s, assigned_to=%s, priority=%s, 
               status=%s, completed_at=%s WHERE id=%s
    """, (title.strip(), due_date or None, assigned_to or None,
          priority, status, completed_at, task_id))
    conn.commit()
    conn.close()


def update_task_status(task_id, status):
    conn = get_conn()
    completed_at = datetime.now().isoformat() if status == "completed" else None
    conn.execute(
        "UPDATE tasks SET status=%s, completed_at=%s WHERE id=%s",
        (status, completed_at, task_id),
    )
    conn.commit()
    conn.close()


def delete_task(task_id):
    conn = get_conn()
    conn.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
    conn.commit()
    conn.close()


# ─── Task Updates ────────────────────────────────────────

def get_due_reminders():
    today_iso = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    conn = get_conn()

    due_today = conn.execute("""
        SELECT t.id, t.title, t.due_date, t.priority, t.status,
               sp.title AS sub_title, sp.id AS sub_id
        FROM tasks t
        JOIN sub_programs sp ON t.sub_program_id = sp.id
        WHERE t.due_date=%s AND t.status NOT IN ('completed', 'on_hold', 'suspended')
        ORDER BY t.priority DESC
    """, (today_iso,)).fetchall()

    due_this_week = conn.execute("""
        SELECT t.id, t.title, t.due_date, t.priority, t.status,
               sp.title AS sub_title, sp.id AS sub_id
        FROM tasks t
        JOIN sub_programs sp ON t.sub_program_id = sp.id
        WHERE t.due_date>%s AND t.due_date<=%s AND t.status NOT IN ('completed', 'on_hold', 'suspended')
        ORDER BY t.due_date, t.priority DESC
    """, (today_iso, week_end)).fetchall()

    conn.close()
    return [dict(r) for r in due_today], [dict(r) for r in due_this_week]


def get_task_updates(task_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_updates WHERE task_id=%s ORDER BY created_at DESC",
        (task_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_task_update(task_id, note):
    conn = get_conn()
    conn.execute(
        "INSERT INTO task_updates (task_id, note) VALUES (%s,%s)",
        (task_id, note.strip()),
    )
    conn.commit()
    conn.close()


def get_linkable_sub_programs():
    """Return non-past-due sub-programs for event/sub-program linking dropdowns."""
    conn = get_conn()
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT sp.*, pc.name AS category_name, m.name AS in_charge_name
        FROM sub_programs sp
        LEFT JOIN program_categories pc ON sp.program_category_id = pc.id
        LEFT JOIN members m ON sp.in_charge_id = m.id
        WHERE sp.due_date IS NULL OR sp.due_date >= %s
        ORDER BY sp.due_date
    """, (today,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Events ──────────────────────────────────────────────

def get_events(year=None, month=None):
    conn = get_conn()
    sql = """SELECT e.*, sp.title AS sub_program_title
             FROM events e
             LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
             WHERE 1=1"""
    params = []
    if year and month:
        sql += " AND EXTRACT(YEAR FROM e.start_date::DATE)=%s AND EXTRACT(MONTH FROM e.start_date::DATE)=%s"
        params.append(year)
        params.append(month)
    sql += " ORDER BY e.start_date"
    rows = conn.execute(sql, params).fetchall()

    events = [dict(r) for r in rows]

    if year and month:
        recurring = conn.execute("""
            SELECT * FROM events
            WHERE recurring_type != 'none' AND sub_program_id IS NULL
        """).fetchall()
        for ev in recurring:
            ev = dict(ev)
            delta = RECURRENCE_DELTA.get(ev["recurring_type"])
            if not delta:
                continue
            seed = datetime.strptime(ev["start_date"][:10], "%Y-%m-%d").date()
            raw = ev.get("expiry_date")
            expiry = datetime.strptime(raw[:10], "%Y-%m-%d").date() if raw else None

            first_of_month = date(year, month, 1)
            if month == 12:
                last_of_month = date(year, 12, 31)
            else:
                last_of_month = date(year, month + 1, 1) - timedelta(days=1)
            gen = 0
            while True:
                inst = seed + delta * gen
                if inst > last_of_month:
                    break
                if expiry and inst > expiry:
                    break
                if inst >= first_of_month and inst.isoformat() != ev["start_date"][:10]:
                    virtual = dict(ev)
                    virtual["start_date"] = inst.isoformat()
                    events.append(virtual)
                gen += 1

    conn.close()
    return events


def get_event(event_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT e.*, sp.title AS sub_program_title
        FROM events e
        LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
        WHERE e.id=%s
    """, (event_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_event(title, sub_program_id, recurring_type, type_flag, start_date, notes, expiry_date=None):
    conn = get_conn()
    sql = ("INSERT INTO events (title, sub_program_id, recurring_type, "
           "type_flag, start_date, expiry_date, notes) "
           "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id")
    cur = conn.execute(sql, (title.strip(), sub_program_id or None, recurring_type,
                             type_flag, start_date, expiry_date or None, notes.strip()))
    event_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return event_id


def update_event(event_id, title, sub_program_id, recurring_type, type_flag,
                 start_date, notes, expiry_date=None):
    conn = get_conn()
    sql = ("UPDATE events SET title=%s, sub_program_id=%s, recurring_type=%s, "
           "type_flag=%s, start_date=%s, expiry_date=%s, notes=%s WHERE id=%s")
    conn.execute(sql, (title.strip(), sub_program_id or None, recurring_type,
                       type_flag, start_date, expiry_date or None, notes.strip(), event_id))
    conn.commit()
    conn.close()


def delete_event(event_id):
    conn = get_conn()
    event = conn.execute("SELECT * FROM events WHERE id=%s", (event_id,)).fetchone()
    if event and event["sub_program_id"]:
        conn.execute(
            "DELETE FROM tasks WHERE sub_program_id=%s AND title=%s",
            (event["sub_program_id"], event["title"]),
        )
    conn.execute("DELETE FROM events WHERE id=%s", (event_id,))
    conn.commit()
    conn.close()


def get_upcoming_schedule(limit=20):
    today_iso = date.today().isoformat()
    schedule = []

    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, due_date AS event_date, type_flag, 'sub_program' AS source
        FROM sub_programs
        WHERE add_to_calendar=1 AND due_date >= %s
        ORDER BY due_date
        LIMIT %s
    """, (today_iso, limit)).fetchall()
    schedule.extend(dict(r) for r in rows)

    rows = conn.execute("""
        SELECT id, title, start_date AS event_date, type_flag, 'event' AS source
        FROM events
        WHERE start_date >= %s
        ORDER BY start_date
        LIMIT %s
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
        WHERE add_to_calendar=1 AND TO_CHAR(due_date::DATE, 'YYYY-MM')=%s
        ORDER BY due_date
    """, (month_start,)).fetchall()
    entries.extend(dict(r) for r in rows)

    rows = conn.execute("""
        SELECT id, title, type_flag, start_date, 'event' AS source
        FROM events
        WHERE recurring_type='none' AND TO_CHAR(start_date::DATE, 'YYYY-MM')=%s
        ORDER BY start_date
    """, (month_start,)).fetchall()
    entries.extend(dict(r) for r in rows)

    _expand_recurring_events(conn, year, month, entries)
    conn.close()
    return entries


def get_calendar_entries_from_date(year, month):
    """Fetch calendar entries from given month onward for sidebar 'Later' card."""
    start_date = date(year, month, 1)
    end_date = start_date + timedelta(days=180)
    entries = []

    conn = get_conn()
    rows = conn.execute("""
        SELECT id, title, type_flag, due_date AS start_date, 'sub_program' AS source
        FROM sub_programs
        WHERE add_to_calendar=1 AND due_date >= %s AND due_date <= %s
        ORDER BY due_date
    """, (start_date.isoformat(), end_date.isoformat())).fetchall()
    entries.extend(dict(r) for r in rows)

    rows = conn.execute("""
        SELECT id, title, type_flag, start_date, 'event' AS source
        FROM events
        WHERE recurring_type='none' AND start_date >= %s AND start_date <= %s
        ORDER BY start_date
    """, (start_date.isoformat(), end_date.isoformat())).fetchall()
    entries.extend(dict(r) for r in rows)

    _expand_recurring_events_in_range(conn, start_date, end_date, entries)
    conn.close()

    seen = set()
    unique = []
    for e in entries:
        key = (e["id"], e["source"], e.get("start_date", "")[:10])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda x: x.get("start_date", ""))
    return unique


def _expand_recurring_events_in_range(conn, start_date, end_date, entries):
    """Expand recurring standalone events into a date range."""
    recurring = conn.execute("""
        SELECT id, title, type_flag, start_date, expiry_date, recurring_type, notes
        FROM events
        WHERE recurring_type != 'none'
    """).fetchall()

    for ev in recurring:
        ev = dict(ev)
        delta = RECURRENCE_DELTA.get(ev["recurring_type"])
        if not delta:
            continue
        seed = datetime.strptime(ev["start_date"][:10], "%Y-%m-%d").date()
        raw_exp = ev.get("expiry_date")
        expiry = datetime.strptime(raw_exp[:10], "%Y-%m-%d").date() if raw_exp else None

        gen = 0
        while True:
            instance_date = seed + delta * gen
            if instance_date > end_date:
                break
            if expiry and instance_date > expiry:
                break
            if instance_date >= start_date and instance_date.isoformat() != ev["start_date"][:10]:
                entries.append({
                    "id": ev["id"],
                    "title": ev["title"],
                    "type_flag": ev["type_flag"],
                    "start_date": instance_date.isoformat(),
                    "source": "event",
                })
            gen += 1


def _expand_recurring_events(conn, year, month, entries):
    """Expand recurring standalone events into a given month, appending to entries list."""
    recurring = conn.execute("""
        SELECT id, title, type_flag, start_date, expiry_date, recurring_type, notes
        FROM events
        WHERE recurring_type != 'none'
    """).fetchall()

    for ev in recurring:
        ev = dict(ev)
        delta = RECURRENCE_DELTA.get(ev["recurring_type"])
        if not delta:
            continue
        seed = datetime.strptime(ev["start_date"][:10], "%Y-%m-%d").date()
        raw_exp = ev.get("expiry_date")
        expiry = datetime.strptime(raw_exp[:10], "%Y-%m-%d").date() if raw_exp else None
        first_of_month = date(year, month, 1)
        if month == 12:
            last_of_month = date(year, 12, 31)
        else:
            last_of_month = date(year, month + 1, 1) - timedelta(days=1)

        gen = 0
        while True:
            instance_date = seed + delta * gen
            if instance_date > last_of_month:
                break
            if expiry and instance_date > expiry:
                break
            if instance_date >= first_of_month:
                entries.append({
                    "id": ev["id"],
                    "title": ev["title"],
                    "type_flag": ev["type_flag"],
                    "start_date": instance_date.isoformat(),
                    "source": "event",
                })
            gen += 1


# ─── Recurrence ──────────────────────────────────────────

RECURRENCE_DELTA = {
    "weekly": timedelta(days=7),
    "bi_weekly": timedelta(days=14),
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=91),
    "annual": timedelta(days=365),
}


def get_next_recurrence_dates(start_date, recurring_type, count=3, expiry_date=None):
    if recurring_type == "none":
        return []
    delta = RECURRENCE_DELTA.get(recurring_type)
    if not delta:
        return []
    seed = datetime.strptime(start_date[:10], "%Y-%m-%d").date()
    expiry = datetime.strptime(expiry_date[:10], "%Y-%m-%d").date() if expiry_date else None
    today = date.today()
    result = []
    gen = 1
    while len(result) < count:
        inst = seed + delta * gen
        if expiry and inst > expiry:
            break
        if inst > today:
            result.append(inst.isoformat())
        gen += 1
        if gen > 100:
            break
    return result


def get_config(key, default=None):
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM app_config WHERE key=%s", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_config (key, value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def generate_recurring_instances(force=False):
    today_dt = date.today()
    today_iso = today_dt.isoformat()
    ref_date = today_dt + timedelta(days=1)
    cutoff_date = ref_date + timedelta(days=7)

    if not force:
        last_check = get_config("last_recurrence_check", "2000-01-01")
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
            if next_date > cutoff_date:
                break
            if next_date < ref_date:
                gen += 1
                continue

            next_iso = next_date.isoformat()

            existing = conn.execute(
                "SELECT id FROM sub_programs WHERE parent_id=%s AND generation=%s",
                (base["id"], gen),
            ).fetchone()
            if existing:
                gen += 1
                continue

            cur = conn.execute("""
                INSERT INTO sub_programs 
                    (program_category_id, title, description, due_date, in_charge_id,
                     recurring_type, add_to_calendar, type_flag, notes, parent_id, generation)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (
                base["program_category_id"], base["title"], base["description"],
                next_iso, base["in_charge_id"], base["recurring_type"],
                base["add_to_calendar"], base["type_flag"], base["notes"],
                base["id"], gen,
            ))
            new_sp_id = cur.fetchone()["id"]

            member_rows = conn.execute(
                "SELECT member_id FROM sub_program_members WHERE sub_program_id=%s",
                (base["id"],),
            ).fetchall()
            for mr in member_rows:
                conn.execute(
                    "INSERT INTO sub_program_members (sub_program_id, member_id) VALUES (%s,%s)",
                    (new_sp_id, mr["member_id"]),
                )

            task_rows = conn.execute(
                "SELECT * FROM tasks WHERE sub_program_id=%s", (base["id"],)
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
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (new_sp_id, tr["title"], task_due, tr["assigned_to"],
                      tr["priority"], "open"))

            if base["add_to_calendar"]:
                conn.execute("""
                    INSERT INTO events (title, sub_program_id, type_flag, start_date, recurring_type, notes)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (base["title"], new_sp_id, base["type_flag"], next_iso,
                      base["recurring_type"], ""))

            created += 1
            gen += 1

    conn.commit()
    conn.close()
    if created:
        set_config("last_recurrence_check", today_iso)
    return created


def count_generated_children(sub_program_id):
    conn = get_conn()
    count_row = conn.execute(
        "SELECT COUNT(*) AS c FROM sub_programs WHERE parent_id=%s",
        (sub_program_id,),
    ).fetchone()
    conn.close()
    return count_row["c"]


# ─── User Management ─────────────────────────────────────

def get_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email=%s", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=%s", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_user(username, email, password, role="viewer", display_name="", is_approved=0):
    from werkzeug.security import generate_password_hash
    conn = get_conn()
    pw_hash = generate_password_hash(password)
    cur = conn.execute(
        "INSERT INTO users (username, email, password_hash, role, display_name, is_approved)"
        " VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (username.strip(), email.strip().lower(), pw_hash, role, display_name.strip(), is_approved),
    )
    uid = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return uid


def update_user(user_id, username, email, role, display_name):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET username=%s, email=%s, role=%s, display_name=%s WHERE id=%s",
        (username.strip(), email.strip().lower(), role, display_name.strip(), user_id),
    )
    conn.commit()
    conn.close()


def update_user_password(user_id, password):
    from werkzeug.security import generate_password_hash
    conn = get_conn()
    pw_hash = generate_password_hash(password)
    conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (pw_hash, user_id))
    conn.commit()
    conn.close()


def set_user_approved(user_id, approved):
    conn = get_conn()
    conn.execute("UPDATE users SET is_approved=%s WHERE id=%s", (1 if approved else 0, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    admin_count_row = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin' AND is_approved=1").fetchone()
    admin_count = admin_count_row["c"]
    if admin_count <= 1:
        target = conn.execute("SELECT role, is_approved FROM users WHERE id=%s", (user_id,)).fetchone()
        if target and target["role"] == "admin" and target["is_approved"]:
            conn.close()
            raise ValueError("Cannot delete the last approved admin user")
    conn.execute("DELETE FROM users WHERE id=%s", (user_id,))
    conn.commit()
    conn.close()


def verify_user(email, password):
    from werkzeug.security import check_password_hash
    user = get_user_by_email(email)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None
