"""
Seed the database with data from sub-programs.xlsx plus members and reasonable defaults.
Run: python3 seed.py
"""
import sys
import os
from datetime import date, timedelta
import openpyxl

sys.path.insert(0, os.path.dirname(__file__))
from models import (
    add_member, add_program_category, add_sub_program, add_sub_program_member,
    add_task, add_event, get_members, get_program_categories,
    get_conn, init_db, set_config,
)

XLSX_PATH = os.path.join(os.path.dirname(__file__), "sub-programs.xlsx")


def seed():
    print("Seeding database from sub-programs.xlsx ...")

    init_db()

    # ── Members (from old Admin & Maintenance sheet knowledge) ──
    members_data = [
        ("Pastor Dinesh", "Pastor", "+94 77 123 4567", ""),
        ("Pastor Dinusha", "Pastor", "", ""),
        ("Pastor Prasad", "Pastor", "", ""),
        ("Pastor Shamika", "Pastor", "", ""),
        ("Rochelle", "Committee Member", "", ""),
        ("Sacha", "Committee Member", "", ""),
        ("Anita", "Committee Member", "", ""),
        ("Seri", "Committee Member", "", ""),
        ("Suren", "Committee Member", "", ""),
        ("Yohan", "Committee Member", "", ""),
        ("Therika", "Committee Member", "", ""),
        ("Rajith", "Committee Member", "", ""),
    ]
    for name, desig, phone, email in members_data:
        add_member(name, desig, phone, email)
    members = get_members()
    member_map = {m["name"].strip().lower(): m["id"] for m in members}
    print(f"  Created {len(members)} members")

    # ── Program Categories ──
    cat_data = [
        ("Programs & Meetings", "Weekly and monthly church programs and meetings", 1),
        ("Ministries & Projects", "Church ministries and ongoing projects", 2),
        ("Admin & Maintenance", "Administrative tasks and building maintenance", 3),
    ]
    for name, desc, sort in cat_data:
        add_program_category(name, desc, sort)
    cats = get_program_categories()
    cat_map = {c["name"].strip().lower(): c["id"] for c in cats}
    print(f"  Created {len(cats)} program categories")

    # ── Read Excel ──
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb.active

    today = date.today()
    next_sunday = today + timedelta(days=(6 - today.weekday()))

    current_category = None
    current_sub_program = None
    sub_programs_created = 0
    tasks_created = 0

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    for row in rows:
        category_name = str(row[0]).strip() if row[0] else ""
        row_type = str(row[1]).strip() if row[1] else ""
        item_name = str(row[2]).strip() if row[2] else ""
        frequency = str(row[3]).strip() if row[3] else ""

        if not item_name:
            continue

        if row_type == "Sub-program":
            cat_key = category_name.strip().lower()
            cat_id = cat_map.get(cat_key)

            if cat_id is None:
                add_program_category(category_name, "", 99)
                cats = get_program_categories()
                cat_map = {c["name"].strip().lower(): c["id"] for c in cats}
                cat_id = cat_map.get(cat_key)

            if not cat_id:
                continue

            current_category = cat_id

            freq_enum = "none"
            if frequency.upper() in ("WEEKLY", "BI_WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL"):
                freq_enum = frequency.lower()

            in_charge = None
            if category_name == "Admin & Maintenance":
                pass
            else:
                mid = current_sub_program % len(members) if current_sub_program else 1
                in_charge = members[mid]["id"] if members else None

            due = None
            if freq_enum == "weekly":
                due = (next_sunday + timedelta(days=7 * sub_programs_created)).isoformat()
            elif freq_enum == "monthly":
                due = (today + timedelta(days=30 * (sub_programs_created + 1))).isoformat()
            elif freq_enum == "quarterly":
                due = (today + timedelta(days=91 * (sub_programs_created + 1))).isoformat()
            else:
                due = (next_sunday + timedelta(days=7 * (sub_programs_created + 1))).isoformat()

            cat_names_lower = [c["name"].strip().lower() for c in cats]
            sp_id = add_sub_program(
                category_id=cat_id,
                title=item_name,
                description=f"",
                due_date=due,
                in_charge_id=in_charge,
                recurring_type=freq_enum,
                add_to_calendar=1 if freq_enum != "none" else 0,
                type_flag="Program",
                notes="",
            )
            current_sub_program = sp_id
            sub_programs_created += 1

            # Add a few members to sub-program
            for m in members[:3]:
                add_sub_program_member(sp_id, m["id"])

        elif row_type == "Task" and current_sub_program:
            due = None
            if current_sub_program:
                sp_due = due if freq_enum != "none" else None

            add_task(
                sub_program_id=current_sub_program,
                title=item_name,
                due_date=sp_due if sub_programs_created < 10 else None,
                assigned_to=members[sub_programs_created % len(members)]["id"],
                priority="medium",
            )
            tasks_created += 1

    wb.close()
    print(f"  Created {sub_programs_created} sub-programs")
    print(f"  Created {tasks_created} tasks")

    # ── Additional Admin & Ministries seed data ──
    conn = get_conn()
    admin_tasks_added = 0
    ministry_tasks_added = 0

    admin_sp = conn.execute("""
        SELECT s.id, s.title FROM sub_programs s
        JOIN program_categories c ON s.program_category_id = c.id
        WHERE c.name = 'Admin & Maintenance'
        ORDER BY s.id
    """).fetchall()

    admin_task_data = {
        "PASTORS AND LEADERS": [
            "Schedule monthly leadership meeting",
            "Prepare ministry progress report",
            "Follow up on leadership action items",
        ],
        "ELDERS": [
            "Review church policies and bylaws",
            "Plan elders quarterly meeting",
            "Address congregation prayer requests",
        ],
        "PLANNING COMMITTEE MEMBERS": [
            "Prepare committee meeting agenda",
            "Review and approve previous minutes",
            "Track and update action items",
        ],
        "OFFCIE STAFF": [
            "Coordinate weekly staff schedule",
            "Manage office supplies inventory",
            "Update office procedures manual",
        ],
        "SOCIAL MEDIA": [
            "Plan weekly social media content",
            "Create engagement report",
            "Update social media calendar",
        ],
        "BUILDING AND MAINTENANCE": [
            "Conduct weekly facility inspection",
            "Schedule necessary repairs",
            "Update building maintenance log",
        ],
    }

    for sp in admin_sp:
        tasks = admin_task_data.get(sp["title"].strip().upper())
        if not tasks:
            continue
        for task_title in tasks:
            add_task(sp["id"], task_title, None, members[len(members) // 2]["id"], "medium")
            admin_tasks_added += 1

    ministry_sp = conn.execute("""
        SELECT s.id, s.title FROM sub_programs s
        JOIN program_categories c ON s.program_category_id = c.id
        WHERE c.name = 'Ministries & Projects'
        ORDER BY s.id
    """).fetchall()

    ministry_task_data = {
        "NEW COMERS": [
            "Welcome and register new members",
            "Assign follow-up partner for each newcomer",
            "Schedule newcomer orientation session",
        ],
        "JDC": [
            "Plan weekly children's program",
            "Recruit and train volunteers",
            "Schedule JDC activities calendar",
        ],
        "YOUNG ADULTS": [
            "Plan monthly young adults event",
            "Coordinate outreach activities",
            "Prepare young adults Bible study",
        ],
        "MENS": [
            "Plan monthly men's fellowship",
            "Organize service projects",
            "Prepare men's ministry meeting agenda",
        ],
    }

    for sp in ministry_sp:
        tasks = ministry_task_data.get(sp["title"].strip().upper())
        if not tasks:
            continue
        for task_title in tasks:
            assignee = members[sub_programs_created % len(members)]["id"]
            add_task(sp["id"], task_title, None, assignee, "medium")
            ministry_tasks_added += 1

    conn.close()

    if admin_tasks_added:
        print(f"  Added {admin_tasks_added} tasks to Admin & Maintenance")
    if ministry_tasks_added:
        print(f"  Added {ministry_tasks_added} tasks to Ministries & Projects")

    # ── Events from Calendar concepts ──
    events_data = [
        ("Youth Sunday", "Event", next_sunday + timedelta(days=7), None),
        ("Leadership Meeting", "Meeting", today + timedelta(days=3), None),
        ("Communion Sunday", "Service", next_sunday + timedelta(days=14), None),
    ]
    for title, tflag, sdate, edate in events_data:
        add_event(title, None, "none", tflag, sdate.isoformat(), "")
    print(f"  Created {len(events_data)} events")

    # ── Init recurrence check ──
    set_config("last_recurrence_check", "2000-01-01")

    print("\nSeed complete!")


if __name__ == "__main__":
    seed()
