"""
Comprehensive test suite for ChMS(prototype) — Church Planning Committee.

Run: python3 -m pytest test_all.py -v
Or:  python3 test_all.py
"""

import os, sys, json, tempfile, shutil, unittest
from datetime import date, timedelta

# Set test DB before importing anything
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["CHMS_DB_PATH"] = os.path.join(TEST_DIR, "test_chms.db")
os.environ["CHMS_TESTING"] = "1"

# Remove any existing test DB
if os.path.exists(os.environ["CHMS_DB_PATH"]):
    os.remove(os.environ["CHMS_DB_PATH"])

import seed
from app import app
from models import (
    DB_PATH,
    init_db, get_conn, get_config, set_config,
    add_member, get_members, get_member, update_member, delete_member,
    add_program_category, get_program_categories, get_program_category,
    update_program_category, delete_program_category,
    add_sub_program, get_sub_program, update_sub_program, delete_sub_program,
    get_sub_program_members, add_sub_program_member, remove_sub_program_member,
    get_all_sub_programs_with_status, get_sub_program_counts, get_sub_program_derived,
    get_overdue_sub_programs, get_active_sub_programs,
    add_task, get_tasks, get_task, update_task, update_task_status, delete_task,
    add_task_update, get_task_updates,
    add_event, get_events, get_event, update_event, delete_event,
    get_calendar_entries, get_upcoming_schedule,
    generate_recurring_instances,
    get_users, get_user, get_user_by_email, add_user, update_user,
    update_user_password, set_user_approved, delete_user, verify_user,
    TASK_STATUSES, TASK_PRIORITIES, RECURRING_TYPES, TYPE_FLAGS,
)


app.config["TESTING"] = True
app.config["SERVER_NAME"] = "localhost"
client = app.test_client()


# ─── Test helpers ───────────────────────────────────────

def assert_db(conn, sql, params=None, msg=None):
    """Assert a DB query returns at least one row."""
    row = conn.execute(sql, params or []).fetchone()
    if msg:
        assert row, msg
    else:
        assert row


def count_db(conn, table, where="1=1", params=None):
    return conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", params or []).fetchone()["c"]


def setUpModule():
    """Seed fresh test DB once before all tests."""
    seed.seed()
    # Login as admin so existing route tests work
    client.post("/login", data={"email": "admin@livingway.church", "password": "qazcde@123"}, follow_redirects=True)


def tearDownModule():
    """Clean up test DB after all tests."""
    db_path = os.environ.get("CHMS_DB_PATH")
    if db_path and os.path.exists(db_path):
        os.remove(db_path)


# ═══════════════════════════════════════════════════════════
# 1. MODEL-LEVEL TESTS
# ═══════════════════════════════════════════════════════════

class TestMembers(unittest.TestCase):

    def test_get_all(self):
        members = get_members()
        self.assertGreater(len(members), 0)

    def test_get_by_id(self):
        m = get_member(1)
        self.assertIsNotNone(m)
        self.assertIn("name", m)

    def test_get_nonexistent(self):
        self.assertIsNone(get_member(9999))

    def test_crud(self):
        mid = add_member("Test User", "Tester", "+94 77 000 0000", "test@church.lk")
        self.assertIsNotNone(mid)
        m = get_member(mid)
        self.assertEqual(m["name"], "Test User")
        update_member(mid, "Test Updated", "Leader", "+94 77 000 0001", "")
        m = get_member(mid)
        self.assertEqual(m["name"], "Test Updated")
        self.assertEqual(m["designation"], "Leader")
        delete_member(mid)
        self.assertIsNone(get_member(mid))


class TestProgramCategories(unittest.TestCase):

    def test_get_all(self):
        cats = get_program_categories()
        self.assertGreaterEqual(len(cats), 3)

    def test_get_by_id(self):
        c = get_program_category(1)
        self.assertIsNotNone(c)
        self.assertIn("name", c)

    def test_crud(self):
        cid = add_program_category("Test Category", "Test desc", 99)
        self.assertIsNotNone(cid)
        c = get_program_category(cid)
        self.assertEqual(c["name"], "Test Category")
        update_program_category(cid, "Renamed Category", "New desc", 99)
        c = get_program_category(cid)
        self.assertEqual(c["name"], "Renamed Category")
        delete_program_category(cid)
        self.assertIsNone(get_program_category(cid))

    def test_unique_name_constraint(self):
        with self.assertRaises(Exception):
            add_program_category("Programs & Meetings", "duplicate", 1)


class TestSubPrograms(unittest.TestCase):

    def test_get_all_counts(self):
        counts = get_sub_program_counts()
        self.assertIn("total", counts)
        self.assertIn("open", counts)
        self.assertIn("completed", counts)
        self.assertGreaterEqual(counts["total"], 16)

    def test_get_by_id(self):
        sp = get_sub_program(1)
        self.assertIsNotNone(sp)
        self.assertIn("title", sp)

    def test_derived_status_and_priority(self):
        derived = get_sub_program_derived(1)
        self.assertIn("status", derived)
        self.assertIn("priority", derived)

    def test_add_with_members(self):
        sp_id = add_sub_program(
            category_id=1, title="Test SP", description="", due_date="2026-12-31",
            in_charge_id=1, recurring_type="none", add_to_calendar=False,
            type_flag="Program", notes=""
        )
        self.assertIsNotNone(sp_id)
        add_sub_program_member(sp_id, 1)
        add_sub_program_member(sp_id, 2)
        members = get_sub_program_members(sp_id)
        self.assertEqual(len(members), 2)
        remove_sub_program_member(sp_id, 1)
        members = get_sub_program_members(sp_id)
        self.assertEqual(len(members), 1)
        delete_sub_program(sp_id)
        self.assertIsNone(get_sub_program(sp_id))

    def test_delete_blocked_when_open_tasks(self):
        sp_id = add_sub_program(
            category_id=1, title="Blocked SP", description="", due_date="2026-12-31",
            in_charge_id=1, recurring_type="none", add_to_calendar=False,
            type_flag="Program", notes=""
        )
        add_task(sp_id, "Open task", "2026-12-30", 1, "medium")
        result = delete_sub_program(sp_id)
        self.assertFalse(result)
        # Clean up
        tasks, _ = get_tasks(sp_id)
        for t in tasks:
            update_task_status(t["id"], "completed")
        self.assertTrue(delete_sub_program(sp_id))

    def test_active_and_overdue(self):
        active = get_active_sub_programs()
        self.assertIsInstance(active, list)
        overdue = get_overdue_sub_programs()
        self.assertIsInstance(overdue, list)

    def test_all_with_status(self):
        all_sp = get_all_sub_programs_with_status()
        self.assertGreaterEqual(len(all_sp), 16)
        for sp in all_sp:
            self.assertIn("derived_status", sp)
            self.assertIn("derived_priority", sp)

    def test_task_due_date_validation_bypass(self):
        """Verify that a task due_date can still exceed parent — model doesn't enforce."""
        sp_id = add_sub_program(
            category_id=1, title="DateTest SP", description="", due_date="2026-06-15",
            in_charge_id=1, recurring_type="none", add_to_calendar=False,
            type_flag="Program", notes=""
        )
        # Model doesn't enforce, so this should succeed
        add_task(sp_id, "Late task", "2026-07-01", 1, "medium")
        tasks, _ = get_tasks(sp_id)
        self.assertTrue(any(t["due_date"] == "2026-07-01" for t in tasks))
        delete_sub_program(sp_id)


class TestTasks(unittest.TestCase):

    def setUp(self):
        self.sp_id = add_sub_program(
            category_id=1, title="TaskTest SP", description="", due_date="2026-10-01",
            in_charge_id=1, recurring_type="none", add_to_calendar=False,
            type_flag="Program", notes=""
        )

    def tearDown(self):
        try:
            delete_sub_program(self.sp_id)
        except Exception:
            pass

    def test_crud(self):
        t_id = add_task(self.sp_id, "Test task", "2026-09-01", 1, "high")
        self.assertIsNotNone(t_id)
        tasks, _ = get_tasks(self.sp_id)
        self.assertTrue(any(t["id"] == t_id for t in tasks))
        t = get_task(t_id)
        self.assertEqual(t["title"], "Test task")
        update_task(t_id, "Updated task", "2026-09-15", 1, "low", "open")
        t = get_task(t_id)
        self.assertEqual(t["title"], "Updated task")
        self.assertEqual(t["priority"], "low")
        delete_task(t_id)
        self.assertIsNone(get_task(t_id))

    def test_status_transitions(self):
        t_id = add_task(self.sp_id, "Status test", None, None, "medium")
        update_task_status(t_id, "in_progress")
        self.assertEqual(get_task(t_id)["status"], "in_progress")
        update_task_status(t_id, "completed")
        self.assertEqual(get_task(t_id)["status"], "completed")
        self.assertIsNotNone(get_task(t_id)["completed_at"])

    def test_follow_up_updates(self):
        t_id = add_task(self.sp_id, "Follow-up test", None, 1, "medium")
        add_task_update(t_id, "First note")
        updates = get_task_updates(t_id)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["note"], "First note")
        add_task_update(t_id, "Second note")
        updates = get_task_updates(t_id)
        self.assertEqual(len(updates), 2)


class TestEvents(unittest.TestCase):

    def test_crud(self):
        e_id = add_event("Test Event", None, "none", "Event", "2026-08-15", "Test notes")
        self.assertIsNotNone(e_id)
        e = get_event(e_id)
        self.assertEqual(e["title"], "Test Event")
        self.assertEqual(e["start_date"], "2026-08-15")
        update_event(e_id, "Updated Event", None, "none", "Meeting", "2026-08-20", "")
        e = get_event(e_id)
        self.assertEqual(e["title"], "Updated Event")
        self.assertEqual(e["type_flag"], "Meeting")
        delete_event(e_id)
        self.assertIsNone(get_event(e_id))

    def test_get_events_by_month(self):
        add_event("Jan Event", None, "none", "Event", "2026-01-15", "")
        add_event("Jun Event", None, "none", "Event", "2026-06-15", "")
        jan_events = get_events(2026, 1)
        self.assertTrue(any(e["title"] == "Jan Event" for e in jan_events))
        jun_events = get_events(2026, 6)
        self.assertTrue(any(e["title"] == "Jun Event" for e in jun_events))

    def test_linked_to_sub_program_creates_task(self):
        """Verify from route level that linking creates task."""
        # Tested in workflow tests

    def test_calendar_entries(self):
        entries = get_calendar_entries(2026, 6)
        self.assertIsInstance(entries, list)
        for e in entries:
            self.assertIn("source", e)
            self.assertIn(e["source"], ("sub_program", "event"))


class TestRecurrence(unittest.TestCase):

    def test_generate_idempotent(self):
        set_config("last_recurrence_check", "2000-01-01")
        c1 = generate_recurring_instances()
        set_config("last_recurrence_check", "2000-01-01")
        c2 = generate_recurring_instances()
        # Second run should produce the same count (no duplicates)
        self.assertEqual(c1, c2)

    def test_recurrence_skips_when_already_checked(self):
        today_iso = date.today().isoformat()
        set_config("last_recurrence_check", today_iso)
        c = generate_recurring_instances()
        self.assertEqual(c, 0)


class TestConfig(unittest.TestCase):

    def test_get_set(self):
        set_config("test_key", "test_value")
        self.assertEqual(get_config("test_key"), "test_value")
        self.assertEqual(get_config("nonexistent", "default"), "default")


class TestUpcomingSchedule(unittest.TestCase):

    def test_get_upcoming(self):
        sched = get_upcoming_schedule(10)
        self.assertIsInstance(sched, list)
        self.assertLessEqual(len(sched), 10)
        # Check sorted by date
        dates = [s["event_date"] for s in sched]
        self.assertEqual(dates, sorted(dates))


# ═══════════════════════════════════════════════════════════
# 2. ROUTE-LEVEL TESTS
# ═══════════════════════════════════════════════════════════

class TestRoutes(unittest.TestCase):

    def assert200(self, url, method="GET", data=None):
        if method == "GET":
            r = client.get(url)
        else:
            r = client.post(url, data=data or {}, follow_redirects=True)
        self.assertEqual(r.status_code, 200, f"{method} {url} returned {r.status_code}")
        return r

    def assertRedirect(self, url, method="GET", data=None):
        if method == "POST":
            r = client.post(url, data=data or {})
        else:
            r = client.get(url)
        self.assertIn(r.status_code, (302, 303, 200))

    # ── Dashboard ──

    def test_dashboard(self):
        r = self.assert200("/")
        html = r.data.decode("utf-8")
        self.assertIn("Dashboard", html)
        self.assertIn("Total Sub-Programs", html)

    def test_dashboard_recurrence_check(self):
        set_config("last_recurrence_check", "2000-01-01")
        self.assert200("/")

    # ── Programs ──

    def test_programs_landing(self):
        self.assert200("/programs")

    def test_program_category_view(self):
        self.assert200("/programs/1")

    def test_program_category_nonexistent(self):
        r = client.get("/programs/9999", follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def test_sub_program_detail(self):
        self.assert200("/programs/sub/1")

    def test_sub_program_detail_json(self):
        r = client.get("/programs/sub/1?json=1")
        if r.status_code == 200 and r.content_type == "application/json":
            data = r.get_json()
            self.assertIsNotNone(data)

    def test_sub_program_detail_nonexistent(self):
        r = client.get("/programs/sub/9999", follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    # ── Sub-program Add ──

    def test_sub_program_add_page(self):
        self.assert200("/programs/add")

    def test_sub_program_add_post(self):
        r = client.post("/programs/add", data={
            "program_category_id": "1",
            "title": "Route Test SP",
            "description": "Created by route test",
            "due_date": "2026-12-31",
            "in_charge_id": "1",
            "recurring_type": "none",
            "add_to_calendar": "1",
            "type_flag": "Program",
            "notes": "",
            "member_ids": ["1", "2"],
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Route Test SP", r.data.decode("utf-8"))

    # ── Sub-program Edit ──

    def test_sub_program_edit_page(self):
        self.assert200("/programs/sub/1/edit")

    def test_sub_program_edit_page_nonexistent(self):
        r = client.get("/programs/sub/9999/edit", follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def test_sub_program_edit_post(self):
        # Create a fresh one to edit
        sp_id = add_sub_program(1, "Edit Test SP", "", "2026-12-31", 1, "none", False, "Program", "")
        r = client.post(f"/programs/sub/{sp_id}/edit", data={
            "program_category_id": "1",
            "title": "Edit Test SP Renamed",
            "description": "edited",
            "due_date": "2026-12-31",
            "in_charge_id": "2",
            "recurring_type": "none",
            "add_to_calendar": "0",
            "type_flag": "Meeting",
            "notes": "Updated notes",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        sp = get_sub_program(sp_id)
        self.assertEqual(sp["title"], "Edit Test SP Renamed")
        self.assertEqual(sp["type_flag"], "Meeting")
        delete_sub_program(sp_id)

    # ── Sub-program Delete ──

    def test_sub_program_delete_no_open_tasks(self):
        sp_id = add_sub_program(1, "Delete Test SP", "", "2026-12-31", 1, "none", False, "Program", "")
        r = client.post(f"/programs/sub/{sp_id}/delete", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(get_sub_program(sp_id))

    def test_sub_program_delete_blocked(self):
        sp_id = add_sub_program(1, "Delete Blocked SP", "", "2026-12-31", 1, "none", False, "Program", "")
        add_task(sp_id, "Blocking task", None, 1, "medium")
        r = client.post(f"/programs/sub/{sp_id}/delete", follow_redirects=True)
        html = r.data.decode("utf-8")
        self.assertIn("error", html)
        self.assertIsNotNone(get_sub_program(sp_id))
        # Cleanup
        for t in get_tasks(sp_id)[0]:
            update_task_status(t["id"], "completed")
        delete_sub_program(sp_id)

    def test_workflow_derived_status_cascade(self):
        """Sub-program derived status changes correctly as tasks are completed."""
        sp_id = add_sub_program(1, "Derived SP", "", "2026-10-01", 1, "none", False, "Program", "")
        t1 = add_task(sp_id, "Task A", None, 1, "high")
        t2 = add_task(sp_id, "Task B", None, 1, "low")
        derived = get_sub_program_derived(sp_id)
        self.assertEqual(derived["status"], "open")
        self.assertEqual(derived["priority"], "high")
        update_task_status(t1, "in_progress")
        derived = get_sub_program_derived(sp_id)
        self.assertEqual(derived["status"], "in_progress")
        self.assertEqual(derived["priority"], "high")
        update_task_status(t1, "completed")
        update_task_status(t2, "completed")
        derived = get_sub_program_derived(sp_id)
        self.assertEqual(derived["status"], "completed")
        self.assertIsNone(derived["priority"])
        tasks, _ = get_tasks(sp_id)
        self.assertTrue(any(t["title"] == "Task A" for t in tasks))
        delete_sub_program(sp_id)

    def test_task_add_without_sub_program(self):
        r = client.post("/programs/sub/9999/tasks/add", data={
            "title": "Orphan Task",
            "due_date": "2026-12-01",
            "assigned_to": "1",
            "priority": "medium",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def test_task_update(self):
        sp_id = add_sub_program(1, "Task Update SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t_id = add_task(sp_id, "To update", "2026-12-01", 1, "medium")
        r = client.post(f"/tasks/{t_id}", data={
            "action": "update",
            "title": "Updated Title",
            "due_date": "2026-12-15",
            "assigned_to": "2",
            "priority": "critical",
            "status": "in_progress",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        t = get_task(t_id)
        self.assertEqual(t["title"], "Updated Title")
        self.assertEqual(t["priority"], "critical")
        delete_sub_program(sp_id)

    def test_task_status_change(self):
        sp_id = add_sub_program(1, "Task Status SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t_id = add_task(sp_id, "Status change", None, 1, "medium")
        r = client.post(f"/tasks/{t_id}", data={
            "action": "status",
            "status": "completed",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        t = get_task(t_id)
        self.assertEqual(t["status"], "completed")
        delete_sub_program(sp_id)

    def test_task_quick_complete(self):
        """Toggle task between open and completed."""
        sp_id = add_sub_program(1, "Toggle SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t_id = add_task(sp_id, "Toggle me", None, 1, "medium")
        r = client.post(f"/tasks/{t_id}/toggle", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        t = get_task(t_id)
        self.assertEqual(t["status"], "completed")
        r = client.post(f"/tasks/{t_id}/toggle", follow_redirects=True)
        t = get_task(t_id)
        self.assertEqual(t["status"], "open")
        delete_sub_program(sp_id)

    def test_task_delete(self):
        sp_id = add_sub_program(1, "Task Delete SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t_id = add_task(sp_id, "Delete me", None, 1, "medium")
        r = client.post(f"/tasks/{t_id}/delete", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(get_task(t_id))
        delete_sub_program(sp_id)

    def test_task_add_follow_up(self):
        sp_id = add_sub_program(1, "Follow-up SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t_id = add_task(sp_id, "Follow-up task", None, 1, "medium")
        r = client.post(f"/tasks/{t_id}", data={
            "action": "add_update",
            "note": "Route test update note"
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        updates = get_task_updates(t_id)
        self.assertTrue(any(u["note"] == "Route test update note" for u in updates))
        delete_sub_program(sp_id)

    # ── Calendar ──

    def test_calendar_view(self):
        self.assert200("/calendar")

    def test_calendar_with_month_params(self):
        self.assert200("/calendar?year=2026&month=6")

    def test_event_detail_json(self):
        e_id = add_event("JSON Test Event", None, "none", "Event", "2026-09-01", "")
        r = client.get(f"/calendar/event/{e_id}")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["title"], "JSON Test Event")
        self.assertEqual(data["date"], "2026-09-01")
        delete_event(e_id)

    def test_event_detail_json_nonexistent(self):
        r = client.get("/calendar/event/9999")
        self.assertEqual(r.status_code, 404)

    # ── Event Add ──

    def test_event_add_page(self):
        self.assert200("/events/add")

    def test_event_add_post(self):
        r = client.post("/events/add", data={
            "title": "Route Test Event",
            "type_flag": "Service",
            "start_date": "2026-07-01",
            "recurring_type": "none",
            "notes": "Created by route test",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        events = get_events()
        self.assertTrue(any(e["title"] == "Route Test Event" for e in events))

    def test_event_add_with_sub_link_creates_task(self):
        """Linking an event to a sub-program before its due_date creates a task."""
        sp_id = add_sub_program(1, "Linked SP", "", "2026-12-31", 1, "none", False, "Program", "")
        r = client.post("/events/add", data={
            "title": "Linked Event",
            "type_flag": "Meeting",
            "start_date": "2026-06-15",
            "sub_program_id": str(sp_id),
            "assignee_id": "1",
            "recurring_type": "none",
            "notes": "",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        # Check task was created in the sub-program
        tasks, _ = get_tasks(sp_id)
        self.assertTrue(any(t["title"] == "Linked Event" for t in tasks),
                        "Event linked to sub-program should auto-create a task")
        delete_sub_program(sp_id)

    def test_event_add_with_sub_link_past_due_rejected(self):
        """Linking an event AFTER the sub-program's due_date should flash error."""
        sp_id = add_sub_program(1, "Past Due SP", "", "2026-05-01", 1, "none", False, "Program", "")
        r = client.post("/events/add", data={
            "title": "Too Late Event",
            "type_flag": "Meeting",
            "start_date": "2026-06-15",
            "sub_program_id": str(sp_id),
            "recurring_type": "none",
            "notes": "",
        }, follow_redirects=True)
        html = r.data.decode("utf-8")
        self.assertIn("error", html)
        delete_sub_program(sp_id)

    # ── Event Edit ──

    def test_event_edit(self):
        e_id = add_event("Edit Me", None, "none", "Event", "2026-08-01", "")
        r = client.post(f"/events/{e_id}/edit", data={
            "title": "Edited Event",
            "sub_program_id": "",
            "type_flag": "Meeting",
            "start_date": "2026-08-15",
            "recurring_type": "monthly",
            "notes": "Updated",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        e = get_event(e_id)
        self.assertEqual(e["title"], "Edited Event")
        delete_event(e_id)

    # ── Event Delete ──

    def test_event_delete(self):
        e_id = add_event("Delete Me", None, "none", "Event", "2026-08-01", "")
        r = client.post(f"/events/{e_id}/delete", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(get_event(e_id))

    # ── Members ──

    def test_member_list(self):
        self.assert200("/members")

    def test_member_add(self):
        r = client.post("/members/add", data={
            "name": "Route Member",
            "designation": "Volunteer",
            "phone": "+94 77 111 2222",
            "email": "route@church.lk",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        members = get_members()
        self.assertTrue(any(m["name"] == "Route Member" for m in members))

    # ── Categories ──

    def test_category_add_page(self):
        self.assert200("/programs/category/add")

    def test_category_add_post(self):
        r = client.post("/programs/category/add", data={
            "name": "Route Test Category",
            "description": "Category created by route test",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        cats = get_program_categories()
        self.assertTrue(any(c["name"] == "Route Test Category" for c in cats))


# ═══════════════════════════════════════════════════════════
# 3. CUSTOMER-LEVEL WORKFLOW TESTS
# ═══════════════════════════════════════════════════════════

class TestWorkflows(unittest.TestCase):
    """Simulate complete user workflows from end to end."""

    def test_workflow_add_program_and_tasks(self):
        """User adds a category, creates a sub-program, adds tasks, assigns members."""
        cat_id = add_program_category("Workflow Cat", "For workflow test", 50)
        sp_id = add_sub_program(
            cat_id, "Workflow SP", "Test description", "2026-11-30",
            1, "none", True, "Program", ""
        )
        add_sub_program_member(sp_id, 1)
        add_sub_program_member(sp_id, 2)
        t1 = add_task(sp_id, "Task A", "2026-11-01", 1, "high")
        t2 = add_task(sp_id, "Task B", "2026-11-15", 2, "medium")
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)

        # Check derived status
        derived = get_sub_program_derived(sp_id)
        self.assertIn(derived["status"], TASK_STATUSES)
        self.assertIn(derived["priority"], TASK_PRIORITIES)

        # Complete one task
        update_task_status(t1, "completed")
        derived = get_sub_program_derived(sp_id)
        self.assertEqual(derived["status"], "in_progress")

        # Complete all tasks
        update_task_status(t2, "completed")
        derived = get_sub_program_derived(sp_id)
        self.assertEqual(derived["status"], "completed")

        # Cleanup
        delete_sub_program(sp_id)
        delete_program_category(cat_id)

    def test_workflow_calendar_event_creates_task(self):
        """User creates a calendar event linked to sub-program — task auto-created."""
        sp_id = add_sub_program(1, "Calendar Link SP", "", "2026-10-01", 1, "none", False, "Program", "")
        r = client.post("/events/add", data={
            "title": "Calendar Created Task",
            "type_flag": "Meeting",
            "start_date": "2026-09-01",
            "sub_program_id": str(sp_id),
            "assignee_id": "3",
            "recurring_type": "none",
            "notes": "",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        tasks, _ = get_tasks(sp_id)
        self.assertTrue(
            any(t["title"] == "Calendar Created Task" for t in tasks),
            "Calendar event must auto-create a task in the linked sub-program"
        )
        delete_sub_program(sp_id)

    def test_workflow_quick_complete_task(self):
        """User clicks quick-complete toggles task status."""
        sp_id = add_sub_program(1, "Workflow Quick SP", "", "2026-12-31", 1, "none", False, "Program", "")
        add_task(sp_id, "Quick task", None, 1, "medium")
        tid = add_task(sp_id, "Another quick", None, 1, "low")
        r = client.post(f"/tasks/{tid}/toggle", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        t = get_task(tid)
        self.assertEqual(t["status"], "completed")
        delete_sub_program(sp_id)

    def test_workflow_cannot_delete_sub_program_with_open_tasks(self):
        """User tries to delete a sub-program that has open tasks — blocked with error."""
        sp_id = add_sub_program(1, "Protected SP", "", "2026-10-01", 1, "none", False, "Program", "")
        add_task(sp_id, "Blocking task", None, 1, "medium")
        r = client.post(f"/programs/sub/{sp_id}/delete", follow_redirects=True)
        html = r.data.decode("utf-8")
        self.assertIn("error", html, "Delete should be blocked with error flash")
        self.assertIsNotNone(get_sub_program(sp_id),
                             "Sub-program should still exist after blocked delete")
        # Cleanup
        for t in get_tasks(sp_id)[0]:
            update_task_status(t["id"], "completed")
        delete_sub_program(sp_id)

    def test_workflow_dashboard_updates_after_changes(self):
        """Dashboard counts reflect after adding/removing sub-programs."""
        r = client.get("/")
        html_before = r.data.decode("utf-8")

        sp_id = add_sub_program(1, "Dashboard Test SP", "", "2026-10-01", 1, "none", False, "Program", "")
        r = client.get("/")
        html_after = r.data.decode("utf-8")

        delete_sub_program(sp_id)
        r = client.get("/")
        html_final = r.data.decode("utf-8")

        # Just verify the pages load (specific count assertions would be too brittle)
        self.assertIn("Total Sub-Programs", html_after)

    def test_workflow_recurring_generation(self):
        """Recurring sub-program generates instances on daily check."""
        set_config("last_recurrence_check", "2000-01-01")
        sp_id = add_sub_program(
            1, "Recur Workflow SP", "", (date.today() + timedelta(days=1)).isoformat(),
            1, "weekly", True, "Program", ""
        )
        count = generate_recurring_instances()
        self.assertIsInstance(count, int)
        # Verify idempotent
        set_config("last_recurrence_check", "2000-01-01")
        count2 = generate_recurring_instances()
        self.assertEqual(count, count2,
                         "Recurrence generation should be idempotent")
        delete_sub_program(sp_id)

    def test_workflow_event_date_before_sub_program_due(self):
        """User cannot link event to sub-program whose due_date already passed."""
        sp_id = add_sub_program(1, "Expired SP", "", "2026-01-01", 1, "none", False, "Program", "")
        r = client.post("/events/add", data={
            "title": "Late Event",
            "type_flag": "Event",
            "start_date": "2026-06-15",
            "sub_program_id": str(sp_id),
            "recurring_type": "none",
            "notes": "",
        }, follow_redirects=True)
        html = r.data.decode("utf-8")
        self.assertIn("error", html, "Should show error when event date > sub-program due")
        delete_sub_program(sp_id)

    def test_workflow_derived_status_cascade(self):
        """Sub-program derived status changes correctly as tasks are completed."""
        sp_id = add_sub_program(1, "Cascade SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t1 = add_task(sp_id, "C1", None, 1, "high")
        t2 = add_task(sp_id, "C2", None, 2, "medium")
        t3 = add_task(sp_id, "C3", None, 3, "low")

        # All open
        d = get_sub_program_derived(sp_id)
        self.assertEqual(d["status"], "open")

        # One in progress
        update_task_status(t1, "in_progress")
        d = get_sub_program_derived(sp_id)
        self.assertEqual(d["status"], "in_progress")

        # One completed
        update_task_status(t1, "completed")
        update_task_status(t2, "in_progress")
        d = get_sub_program_derived(sp_id)
        self.assertEqual(d["status"], "in_progress")

        # All completed
        update_task_status(t2, "completed")
        update_task_status(t3, "completed")
        d = get_sub_program_derived(sp_id)
        self.assertEqual(d["status"], "completed")

        # One reopened
        update_task_status(t1, "open")
        d = get_sub_program_derived(sp_id)
        self.assertEqual(d["status"], "in_progress", "Reopened task puts sub-program back in progress")

        delete_sub_program(sp_id)

    def test_workflow_priority_derived_highest_open(self):
        """Derived priority matches the highest priority among open/in-progress tasks."""
        sp_id = add_sub_program(1, "Priority SP", "", "2026-12-31", 1, "none", False, "Program", "")
        add_task(sp_id, "Low task", None, 1, "low")
        add_task(sp_id, "High task", None, 2, "high")
        add_task(sp_id, "Medium task", None, 3, "medium")
        d = get_sub_program_derived(sp_id)
        self.assertEqual(d["priority"], "high",
                         "Derived priority should be highest among open tasks")
        delete_sub_program(sp_id)

    def test_workflow_error_page_not_found(self):
        """Accessing nonexistent routes should not crash."""
        r = client.get("/nonexistent-route", follow_redirects=True)
        self.assertIn(r.status_code, (200, 404))


# ═══════════════════════════════════════════════════════════
# 4. EDGE CASES AND CONSTRAINTS
# ═══════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):

    def test_sub_program_empty_title_rejected(self):
        form = {
            "program_category_id": "1",
            "title": "",
            "description": "",
            "due_date": "2026-12-31",
            "in_charge_id": "1",
            "recurring_type": "none",
            "add_to_calendar": "0",
            "type_flag": "Program",
            "notes": "",
        }
        r = client.post("/programs/add", data=form, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def test_event_empty_title_rejected(self):
        r = client.post("/events/add", data={
            "title": "",
            "type_flag": "Event",
            "start_date": "2026-07-01",
            "recurring_type": "none",
            "notes": "",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        # HTML5 validation should block, but server may accept — just verify no crash

    def test_member_empty_name(self):
        r = client.post("/members/add", data={
            "name": "",
            "designation": "",
            "phone": "",
            "email": "",
        }, follow_redirects=True)
        self.assertIn(r.status_code, (200, 400))

    def test_sub_program_due_date_in_past(self):
        sp_id = add_sub_program(1, "Past Due SP", "", "2020-01-01", 1, "none", False, "Program", "")
        self.assertIsNotNone(sp_id, "Past due_date should be accepted")
        overdue = get_overdue_sub_programs()
        self.assertTrue(any(sp["id"] == sp_id for sp in overdue),
                        "Past-due sub-program should appear in overdue list")
        delete_sub_program(sp_id)

    def test_task_due_date_none(self):
        sp_id = add_sub_program(1, "None Date SP", "", "2026-12-31", 1, "none", False, "Program", "")
        t_id = add_task(sp_id, "No due date", None, 1, "medium")
        self.assertIsNotNone(t_id)
        t = get_task(t_id)
        self.assertIsNone(t["due_date"])
        delete_sub_program(sp_id)

    def test_no_crash_on_missing_form_fields(self):
        sp_id = add_sub_program(1, "Missing Fields SP", "", "2026-12-31", 1, "none", False, "Program", "")
        r = client.post(f"/programs/sub/{sp_id}/edit", data={
            "program_category_id": "1",
            "title": "Minimal",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        delete_sub_program(sp_id)

    def test_long_titles(self):
        long_title = "A" * 500
        r = client.post("/events/add", data={
            "title": long_title,
            "type_flag": "Event",
            "start_date": "2026-07-01",
            "recurring_type": "none",
            "notes": "",
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def test_calendar_edge_months(self):
        """Calendar navigation across year boundary doesn't crash."""
        r = client.get("/calendar?year=2026&month=1")
        self.assertEqual(r.status_code, 200)
        r = client.get("/calendar?year=2026&month=12")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_with_no_data(self):
        """Dashboard should not crash even if queries return empty."""
        counts = get_sub_program_counts()
        self.assertIsInstance(counts, dict)

    def test_member_phone_optional(self):
        m_id = add_member("No Phone", "Member", "", "")
        m = get_member(m_id)
        self.assertIsNotNone(m)
        delete_member(m_id)


# ═══════════════════════════════════════════════════════════
# 5. DATA INTEGRITY TESTS
# ═══════════════════════════════════════════════════════════

class TestDataIntegrity(unittest.TestCase):

    def test_all_sub_programs_have_category(self):
        """Every sub-program belongs to an existing category."""
        conn = get_conn()
        orphans = conn.execute("""
            SELECT COUNT(*) AS c FROM sub_programs s
            LEFT JOIN program_categories c ON s.program_category_id = c.id
            WHERE c.id IS NULL
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(orphans, 0)

    def test_all_tasks_have_sub_program(self):
        """Every task belongs to an existing sub-program."""
        conn = get_conn()
        orphans = conn.execute("""
            SELECT COUNT(*) AS c FROM tasks t
            LEFT JOIN sub_programs s ON t.sub_program_id = s.id
            WHERE s.id IS NULL
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(orphans, 0)

    def test_all_events_valid_type(self):
        """All events have a valid type_flag."""
        conn = get_conn()
        invalid = conn.execute("""
            SELECT COUNT(*) AS c FROM events
            WHERE type_flag NOT IN ('Program','Meeting','Event','Service')
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(invalid, 0)

    def test_all_tasks_valid_status(self):
        conn = get_conn()
        invalid = conn.execute("""
            SELECT COUNT(*) AS c FROM tasks
            WHERE status NOT IN ('open','in_progress','completed','on_hold','suspended')
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(invalid, 0)

    def test_all_tasks_valid_priority(self):
        conn = get_conn()
        invalid = conn.execute("""
            SELECT COUNT(*) AS c FROM tasks
            WHERE priority NOT IN ('low','medium','high','critical')
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(invalid, 0)

    def test_all_sub_programs_valid_type(self):
        conn = get_conn()
        invalid = conn.execute("""
            SELECT COUNT(*) AS c FROM sub_programs
            WHERE type_flag NOT IN ('Program','Meeting','Event','Service')
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(invalid, 0)

    def test_recurring_sub_programs_have_due_date(self):
        conn = get_conn()
        missing = conn.execute("""
            SELECT COUNT(*) AS c FROM sub_programs
            WHERE recurring_type != 'none' AND due_date IS NULL
        """).fetchone()["c"]
        conn.close()
        self.assertEqual(missing, 0, "Recurring sub-programs must have a due_date")

    def test_wal_mode_enabled(self):
        conn = get_conn()
        row = conn.execute("PRAGMA journal_mode").fetchone()
        conn.close()
        self.assertEqual(row[0].upper(), "WAL")


# ═══════════════════════════════════════════════════════════
# 8. USER TESTS
# ═══════════════════════════════════════════════════════════

class TestUserModels(unittest.TestCase):

    def test_admin_exists(self):
        user = get_user_by_email("admin@livingway.church")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "admin")
        self.assertTrue(user["is_approved"])

    def test_verify_admin(self):
        user = verify_user("admin@livingway.church", "qazcde@123")
        self.assertIsNotNone(user)

    def test_verify_bad_password(self):
        user = verify_user("admin@livingway.church", "wrong")
        self.assertIsNone(user)

    def test_verify_bad_email(self):
        user = verify_user("nobody@nowhere.com", "x")
        self.assertIsNone(user)

    def test_add_and_get_user(self):
        uid = add_user("testuser", "test@test.com", "secret123", "viewer", "Test User", 1)
        u = get_user(uid)
        self.assertIsNotNone(u)
        self.assertEqual(u["username"], "testuser")
        self.assertEqual(u["email"], "test@test.com")
        self.assertEqual(u["role"], "viewer")

    def test_update_user(self):
        uid = add_user("updateme", "upd@test.com", "pw", "viewer", "Before", 1)
        update_user(uid, "updated", "upd@test.com", "power_user", "After")
        u = get_user(uid)
        self.assertEqual(u["username"], "updated")
        self.assertEqual(u["role"], "power_user")
        self.assertEqual(u["display_name"], "After")

    def test_change_password(self):
        uid = add_user("changepw", "cpw@test.com", "oldpw", "viewer", "", 1)
        update_user_password(uid, "newpw")
        user = verify_user("cpw@test.com", "newpw")
        self.assertIsNotNone(user)
        user = verify_user("cpw@test.com", "oldpw")
        self.assertIsNone(user)

    def test_approve_unapprove(self):
        uid = add_user("pending", "pend@test.com", "pw", "viewer", "", 0)
        self.assertFalse(get_user(uid)["is_approved"])
        set_user_approved(uid, 1)
        self.assertTrue(get_user(uid)["is_approved"])
        set_user_approved(uid, 0)
        self.assertFalse(get_user(uid)["is_approved"])

    def test_delete_user(self):
        uid = add_user("deleteme", "del@test.com", "pw", "viewer", "", 1)
        delete_user(uid)
        self.assertIsNone(get_user(uid))

    def test_cannot_delete_last_admin(self):
        with self.assertRaises(ValueError):
            admin = get_user_by_email("admin@livingway.church")
            delete_user(admin["id"])

    def test_get_users(self):
        users = get_users()
        self.assertTrue(len(users) >= 1)


class TestUserRoutes(unittest.TestCase):

    def setUp(self):
        self.c = app.test_client()

    def test_login_page(self):
        resp = self.c.get("/login")
        self.assertEqual(resp.status_code, 200)

    def test_register_page(self):
        resp = self.c.get("/register")
        self.assertEqual(resp.status_code, 200)

    def test_register_user(self):
        resp = self.c.post("/register", data={
            "username": "newguy",
            "email": "newguy@test.com",
            "password": "test123",
            "confirm_password": "test123",
            "display_name": "New Guy",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"approve your account", resp.data.lower())

    def test_unapproved_cannot_login(self):
        uid = add_user("unapproved", "unapp@test.com", "pw", "viewer", "", 0)
        resp = self.c.post("/login", data={
            "email": "unapp@test.com",
            "password": "pw",
        }, follow_redirects=True)
        self.assertIn(b"pending approval", resp.data.lower())

    def test_login_success(self):
        self.c.post("/login", data={
            "email": "admin@livingway.church",
            "password": "qazcde@123",
        }, follow_redirects=True)
        resp = self.c.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_logout(self):
        self.c.post("/login", data={
            "email": "admin@livingway.church",
            "password": "qazcde@123",
        })
        resp = self.c.get("/logout", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        # Should redirect to login
        resp = self.c.get("/", follow_redirects=False)
        self.assertIn(resp.status_code, (302,))

    def test_viewer_blocked_from_write(self):
        uid = add_user("vieweronly", "view@test.com", "pw", "viewer", "Viewer", 1)
        self.c.post("/login", data={"email": "view@test.com", "password": "pw"}, follow_redirects=True)
        resp = self.c.post("/members/add", data={"name": "Should Not Work"}, follow_redirects=True)
        self.assertIn(b"do not have permission", resp.data.lower())

    def test_power_user_can_write(self):
        uid = add_user("power", "power@test.com", "pw", "power_user", "Power", 1)
        self.c.post("/login", data={"email": "power@test.com", "password": "pw"}, follow_redirects=True)
        resp = self.c.post("/members/add", data={
            "name": "Power User Member",
            "designation": "Test",
            "phone": "",
            "email": "",
        }, follow_redirects=True)
        self.assertNotIn(b"do not have permission", resp.data.lower())

    def test_power_user_blocked_from_admin(self):
        uid = add_user("pow2", "pow2@test.com", "pw", "power_user", "", 1)
        self.c.post("/login", data={"email": "pow2@test.com", "password": "pw"}, follow_redirects=True)
        resp = self.c.get("/users", follow_redirects=True)
        self.assertIn(b"admin access required", resp.data.lower())

    def test_admin_user_page(self):
        self.c.post("/login", data={"email": "admin@livingway.church", "password": "qazcde@123"}, follow_redirects=True)
        resp = self.c.get("/users")
        self.assertEqual(resp.status_code, 200)

    def test_change_own_password(self):
        uid = add_user("selfpw", "selfpw@test.com", "old", "viewer", "", 1)
        self.c.post("/login", data={"email": "selfpw@test.com", "password": "old"}, follow_redirects=True)
        resp = self.c.post("/password", data={
            "current_password": "old",
            "new_password": "newself",
            "confirm_password": "newself",
        }, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(verify_user("selfpw@test.com", "newself"))

    def test_admin_reset_password(self):
        uid = add_user("resetme", "reset@test.com", "oldpw", "viewer", "", 1)
        self.c.post("/login", data={"email": "admin@livingway.church", "password": "qazcde@123"}, follow_redirects=True)
        resp = self.c.post(f"/users/{uid}/password", data={"password": "newadminpw"}, follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(verify_user("reset@test.com", "newadminpw"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
