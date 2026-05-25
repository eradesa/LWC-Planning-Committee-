import os
import sys
import webbrowser
import json
from threading import Timer
from datetime import datetime, date, timedelta
from calendar import monthcalendar

from flask import (
    Flask, render_template, request, redirect,
    url_for, jsonify, flash
)

from models import (
    generate_recurring_instances,
    get_members, get_member, add_member, update_member, delete_member,
    get_program_categories, get_program_category,
    add_program_category, update_program_category, delete_program_category,
    get_sub_program, add_sub_program, update_sub_program, delete_sub_program,
    get_sub_program_members, add_sub_program_member, remove_sub_program_member,
    get_all_sub_programs_with_status, get_sub_program_counts,
    get_sub_program_derived,
    get_overdue_sub_programs, get_active_sub_programs,
    get_tasks, get_task, add_task, update_task, update_task_status, delete_task,
    get_task_updates as _get_task_updates, add_task_update,
    get_events, get_event, add_event, update_event, delete_event,
    get_calendar_entries, get_upcoming_schedule,
    TASK_STATUSES, TASK_PRIORITIES, RECURRING_TYPES, TYPE_FLAGS,
)

app = Flask(__name__)
app.secret_key = "chms-secret-key"

LAST_RECURRENCE_CHECK = None


@app.template_global()
def today():
    return date.today().isoformat()


@app.template_global()
def status_color(status):
    return {
        "open": "badge-open",
        "in_progress": "badge-progress",
        "completed": "badge-done",
        "on_hold": "badge-hold",
        "suspended": "badge-suspended",
    }.get(status, "")


@app.template_global()
def priority_color(priority):
    return {
        "low": "badge-low",
        "medium": "badge-med",
        "high": "badge-high",
        "critical": "badge-critical",
    }.get(priority, "")


@app.template_global()
def get_task_updates(task_id):
    return _get_task_updates(task_id)


@app.before_request
def check_recurrence():
    global LAST_RECURRENCE_CHECK
    today_iso = date.today().isoformat()
    if LAST_RECURRENCE_CHECK != today_iso:
        created = generate_recurring_instances()
        if created:
            print(f"Recurrence: generated {created} new sub-program(s)")
        LAST_RECURRENCE_CHECK = today_iso


# ─── Dashboard ──────────────────────────────────────────

@app.route("/")
def dashboard():
    counts = get_sub_program_counts()
    overdue_subs = get_overdue_sub_programs()
    active_subs = get_active_sub_programs()
    schedule = get_upcoming_schedule(20)
    categories = get_program_categories()

    return render_template(
        "dashboard.html",
        counts=counts,
        overdue_subs=overdue_subs,
        active_subs=active_subs,
        schedule=schedule,
        categories=categories,
    )


# ─── Programs ───────────────────────────────────────────

@app.route("/programs")
def programs_landing():
    categories = get_program_categories()
    for c in categories:
        subs = get_all_sub_programs_with_status(category_id=c["id"])
        c["sub_count"] = len(subs)
        c["active_count"] = sum(1 for s in subs if s["derived_status"] != "completed")
    return render_template("programs.html", categories=categories)


@app.route("/programs/<int:cat_id>")
def program_category(cat_id):
    category = get_program_category(cat_id)
    if not category:
        flash("Category not found", "error")
        return redirect(url_for("programs_landing"))
    search = request.args.get("search", "")
    subs = get_all_sub_programs_with_status(category_id=cat_id, search=search)
    members = get_members()
    categories = get_program_categories()
    return render_template(
        "category.html",
        category=category, subs=subs,
        members=members, categories=categories,
        search=search,
        recurring_types=RECURRING_TYPES,
        type_flags=TYPE_FLAGS,
    )


@app.route("/programs/sub/<int:sub_id>")
def sub_program_detail(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    derived = get_sub_program_derived(sub_id)
    tasks = get_tasks(sub_id)
    team = get_sub_program_members(sub_id)
    members = get_members()
    categories = get_program_categories()
    return render_template(
        "sub_program.html",
        sub=sub, derived=derived, tasks=tasks,
        team=team, members=members, categories=categories,
        statuses=TASK_STATUSES, priorities=TASK_PRIORITIES,
    )


@app.route("/programs/add", methods=["GET", "POST"])
def sub_program_add():
    if request.method == "POST":
        sub_id = add_sub_program(
            category_id=int(request.form["program_category_id"]),
            title=request.form["title"],
            description=request.form.get("description", ""),
            due_date=request.form.get("due_date") or None,
            in_charge_id=request.form.get("in_charge_id", type=int),
            recurring_type=request.form.get("recurring_type", "none"),
            add_to_calendar=request.form.get("add_to_calendar", "0") == "1",
            type_flag=request.form.get("type_flag", "Program"),
            notes=request.form.get("notes", ""),
        )

        member_ids = request.form.getlist("member_ids")
        for mid in member_ids:
            add_sub_program_member(sub_id, int(mid))

        flash("Sub-program created", "success")
        return redirect(url_for("program_category", cat_id=request.form["program_category_id"]))
    members = get_members()
    categories = get_program_categories()
    return render_template(
        "sub_program_form.html", sub=None,
        members=members, categories=categories,
        recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
    )


@app.route("/programs/sub/<int:sub_id>/edit", methods=["GET", "POST"])
def sub_program_edit(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    if request.method == "POST":
        update_sub_program(
            sub_id=sub_id,
            category_id=int(request.form["program_category_id"]),
            title=request.form["title"],
            description=request.form.get("description", ""),
            due_date=request.form.get("due_date") or None,
            in_charge_id=request.form.get("in_charge_id", type=int),
            recurring_type=request.form.get("recurring_type", "none"),
            add_to_calendar=request.form.get("add_to_calendar", "0") == "1",
            type_flag=request.form.get("type_flag", "Program"),
            notes=request.form.get("notes", ""),
        )
        # Update members
        conn = None
        try:
            from models import get_conn
            conn = get_conn()
            conn.execute("DELETE FROM sub_program_members WHERE sub_program_id=?", (sub_id,))
            member_ids = request.form.getlist("member_ids")
            for mid in member_ids:
                conn.execute(
                    "INSERT INTO sub_program_members (sub_program_id, member_id) VALUES (?,?)",
                    (sub_id, int(mid)),
                )
            conn.commit()
        finally:
            if conn:
                conn.close()

        flash("Sub-program updated", "success")
        return redirect(url_for("sub_program_detail", sub_id=sub_id))

    team = get_sub_program_members(sub_id)
    team_ids = [m["id"] for m in team]
    members = get_members()
    categories = get_program_categories()
    return render_template(
        "sub_program_form.html", sub=sub, team_ids=team_ids,
        members=members, categories=categories,
        recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
    )


@app.route("/programs/sub/<int:sub_id>/delete", methods=["POST"])
def sub_program_delete(sub_id):
    success = delete_sub_program(sub_id)
    if success:
        flash("Sub-program deleted", "success")
    else:
        flash("Cannot delete: some tasks are still Open or In-Progress", "error")
    return redirect(url_for("programs_landing"))


@app.route("/programs/sub/<int:sub_id>/note", methods=["POST"])
def sub_program_add_note(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    notes = request.form.get("notes", "")
    conn = None
    try:
        from models import get_conn
        conn = get_conn()
        conn.execute("UPDATE sub_programs SET notes=?, updated_at=datetime('now') WHERE id=?",
                     (notes, sub_id))
        conn.commit()
    finally:
        if conn:
            conn.close()
    flash("Notes saved", "success")
    return redirect(url_for("sub_program_detail", sub_id=sub_id))


# ─── Tasks ──────────────────────────────────────────────

@app.route("/programs/sub/<int:sub_id>/tasks/add", methods=["POST"])
def task_add(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    add_task(
        sub_program_id=sub_id,
        title=request.form["title"],
        due_date=request.form.get("due_date") or None,
        assigned_to=request.form.get("assigned_to", type=int),
        priority=request.form.get("priority", "medium"),
    )
    flash("Task created", "success")
    return redirect(url_for("sub_program_detail", sub_id=sub_id))


@app.route("/tasks/<int:tid>", methods=["POST"])
def task_update(tid):
    task = get_task(tid)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("programs_landing"))
    action = request.form.get("action")
    if action == "update":
        update_task(
            task_id=tid,
            title=request.form["title"],
            due_date=request.form.get("due_date") or None,
            assigned_to=request.form.get("assigned_to", type=int),
            priority=request.form.get("priority", "medium"),
            status=request.form.get("status", "open"),
        )
        flash("Task updated", "success")
    elif action == "add_update":
        add_task_update(tid, request.form.get("note", ""))
        flash("Follow-up added", "success")
    elif action == "status":
        update_task_status(tid, request.form.get("status", "open"))
        flash("Status updated", "success")
    return redirect(url_for("sub_program_detail", sub_id=task["sub_program_id"]))


@app.route("/tasks/<int:tid>/delete", methods=["POST"])
def task_delete(tid):
    task = get_task(tid)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("programs_landing"))
    delete_task(tid)
    flash("Task deleted", "success")
    return redirect(url_for("sub_program_detail", sub_id=task["sub_program_id"]))


# ─── Calendar ───────────────────────────────────────────

@app.route("/calendar")
def calendar_view():
    today_dt = date.today()
    year = request.args.get("year", today_dt.year, type=int)
    month = request.args.get("month", today_dt.month, type=int)

    entries = get_calendar_entries(year, month)
    cal = monthcalendar(year, month)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    entries_by_date = {}
    for e in entries:
        d = e["start_date"][:10]
        entries_by_date.setdefault(d, []).append(e)

    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1

    month_entries = get_calendar_entries(year, month)
    month_events = get_events(year=year, month=month)
    members = get_members()
    categories = get_program_categories()

    return render_template(
        "calendar.html",
        cal=cal, day_names=day_names,
        year=year, month=month,
        next_month=next_month, next_year=next_year,
        prev_month=prev_month, prev_year=prev_year,
        today=today_dt.isoformat(),
        entries_by_date=entries_by_date,
        month_entries=month_entries,
        month_events=month_events,
        members=members, categories=categories,
        months=[
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
    )


@app.route("/calendar/event/<int:eid>")
def event_detail(eid):
    event = get_event(eid)
    if not event:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "id": event["id"],
        "title": event["title"],
        "type_flag": event["type_flag"],
        "date": event["start_date"],
        "notes": event["notes"],
        "sub_program_title": event.get("sub_program_title"),
    })


@app.route("/events/add", methods=["GET", "POST"])
def event_add():
    if request.method == "POST":
        start_date = request.form["start_date"]
        sub_id = request.form.get("sub_program_id", type=int)

        if sub_id:
            from models import get_sub_program
            sp = get_sub_program(sub_id)
            if sp and sp["due_date"] and sp["due_date"] < start_date:
                flash("Event date cannot be after the linked sub-program's due date", "error")
                subs = get_all_sub_programs_with_status()
                members = get_members()
                return render_template(
                    "event_form.html", event=None,
                    subs=subs, members=members,
                    recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
                )

        event_id = add_event(
            title=request.form["title"],
            sub_program_id=sub_id,
            recurring_type=request.form.get("recurring_type", "none"),
            type_flag=request.form.get("type_flag", "Event"),
            start_date=start_date,
            notes=request.form.get("notes", ""),
        )

        # If linked to sub-program and assignee chosen, create task
        assignee = request.form.get("assignee_id", type=int)
        if sub_id and event_id:
            add_task(
                sub_program_id=sub_id,
                title=request.form["title"],
                due_date=start_date,
                assigned_to=assignee,
                priority="medium",
            )

        flash("Event added", "success")
        return redirect(url_for("calendar_view"))

    subs = get_all_sub_programs_with_status()
    members = get_members()
    return render_template(
        "event_form.html", event=None,
        subs=subs, members=members,
        recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
    )


@app.route("/events/<int:eid>/edit", methods=["POST"])
def event_edit(eid):
    event = get_event(eid)
    if not event:
        flash("Event not found", "error")
        return redirect(url_for("calendar_view"))
    update_event(
        event_id=eid,
        title=request.form["title"],
        sub_program_id=request.form.get("sub_program_id", type=int),
        recurring_type=request.form.get("recurring_type", "none"),
        type_flag=request.form.get("type_flag", "Event"),
        start_date=request.form["start_date"],
        notes=request.form.get("notes", ""),
    )
    flash("Event updated", "success")
    return redirect(url_for("calendar_view"))


@app.route("/events/<int:eid>/delete", methods=["POST"])
def event_delete(eid):
    delete_event(eid)
    flash("Event deleted", "success")
    return redirect(url_for("calendar_view"))


# ─── Program Categories ─────────────────────────────────

@app.route("/programs/category/add", methods=["GET", "POST"])
def category_add():
    if request.method == "POST":
        add_program_category(
            name=request.form["name"],
            description=request.form.get("description", ""),
            sort_order=int(request.form.get("sort_order", 0)),
        )
        flash("Program category added", "success")
        return redirect(url_for("programs_landing"))
    return render_template("category_form.html", category=None)


@app.route("/programs/category/<int:cat_id>/edit", methods=["POST"])
def category_edit(cat_id):
    cat = get_program_category(cat_id)
    if not cat:
        flash("Category not found", "error")
        return redirect(url_for("programs_landing"))
    update_program_category(
        category_id=cat_id,
        name=request.form["name"],
        description=request.form.get("description", ""),
        sort_order=int(request.form.get("sort_order", 0)),
    )
    flash("Category updated", "success")
    return redirect(url_for("programs_landing"))


@app.route("/programs/category/<int:cat_id>/delete", methods=["POST"])
def category_delete(cat_id):
    delete_program_category(cat_id)
    flash("Category deleted", "success")
    return redirect(url_for("programs_landing"))


# ─── Members / Directory ─────────────────────────────────

@app.route("/members")
def member_list():
    members = get_members()
    categories = get_program_categories()
    return render_template("members.html", members=members, categories=categories)


@app.route("/members/add", methods=["GET", "POST"])
def member_add():
    if request.method == "POST":
        add_member(
            name=request.form["name"],
            designation=request.form.get("designation", ""),
            phone=request.form.get("phone", ""),
            email=request.form.get("email", ""),
        )
        flash("Member added", "success")
        return redirect(url_for("member_list"))
    return render_template("member_form.html", member=None)


@app.route("/members/<int:mid>/edit", methods=["GET", "POST"])
def member_edit(mid):
    member = get_member(mid)
    if not member:
        flash("Member not found", "error")
        return redirect(url_for("member_list"))
    if request.method == "POST":
        update_member(
            member_id=mid,
            name=request.form["name"],
            designation=request.form.get("designation", ""),
            phone=request.form.get("phone", ""),
            email=request.form.get("email", ""),
        )
        flash("Member updated", "success")
        return redirect(url_for("member_list"))
    return render_template("member_form.html", member=member)


@app.route("/members/<int:mid>/delete", methods=["POST"])
def member_delete(mid):
    delete_member(mid)
    flash("Member deleted", "success")
    return redirect(url_for("member_list"))


# ─── Bootstrap ───────────────────────────────────────────

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")


if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1.5, open_browser).start()
    port = int(os.environ.get("PORT", 5000))
    print(f"ChMS(prototype) starting at http://127.0.0.1:{port}")
    print("Close terminal or press Ctrl+C to stop.")
    app.run(host="127.0.0.1", port=port, debug=False)
