import os
import sys
import csv
import webbrowser
import json
from threading import Timer
from datetime import datetime, date, timedelta
from calendar import monthcalendar

from flask import (
    Flask, render_template, request, redirect,
    url_for, jsonify, flash, session
)

from models import (
    generate_recurring_instances,
    count_generated_children,
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
    get_calendar_entries, get_upcoming_schedule, get_due_reminders,
    get_next_recurrence_dates,
    get_users, get_user, get_user_by_email, get_user_by_username,
    add_user, update_user, update_user_password, set_user_approved, delete_user,
    verify_user,
    TASK_STATUSES, TASK_PRIORITIES, RECURRING_TYPES, TYPE_FLAGS,
    DB_PATH, get_data_dir, get_conn,
)

base_path = getattr(sys, '_MEIPASS', os.path.dirname(__file__))
app = Flask(__name__,
    template_folder=os.path.join(base_path, 'templates'),
    static_folder=os.path.join(base_path, 'static'))
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


# ─── Auth helpers & decorators ──────────────────────────

@app.context_processor
def inject_current_user():
    uid = session.get("user_id")
    user = get_user(uid) if uid else None
    return dict(current_user=user)


from functools import wraps


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = get_user(session["user_id"])
        if not user or not user["is_approved"]:
            session.clear()
            flash("Your account is pending approval", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def require_write(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        user = get_user(session["user_id"])
        if user["role"] not in ("admin", "power_user"):
            flash("You do not have permission to write data", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


def require_admin(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        user = get_user(session["user_id"])
        if user["role"] != "admin":
            flash("Admin access required", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.before_request
def check_recurrence():
    global LAST_RECURRENCE_CHECK
    today_iso = date.today().isoformat()
    if LAST_RECURRENCE_CHECK != today_iso:
        created = generate_recurring_instances()
        if created:
            print(f"Recurrence: generated {created} new sub-program(s)")
        LAST_RECURRENCE_CHECK = today_iso


# ─── Auth Routes ─────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = verify_user(email, password)
        if user:
            if not user["is_approved"]:
                flash("Your account is pending approval by an admin", "error")
                return render_template("login.html")
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['display_name'] or user['username']}", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        display_name = request.form.get("display_name", "").strip()

        if not username or not email or not password:
            flash("All fields are required", "error")
            return render_template("register.html")
        if password != confirm:
            flash("Passwords do not match", "error")
            return render_template("register.html")
        if get_user_by_email(email):
            flash("Email already registered", "error")
            return render_template("register.html")
        if get_user_by_username(username):
            flash("Username already taken", "error")
            return render_template("register.html")

        add_user(username, email, password, "viewer", display_name, 0)
        flash("Registration submitted. An admin must approve your account.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("login"))


# ─── User Management (admin) ────────────────────────────

@app.route("/users")
@require_admin
def user_list():
    users = get_users()
    cats = get_program_categories()
    return render_template("users.html", users=users, categories=cats)


@app.route("/users/add", methods=["GET", "POST"])
@require_admin
def user_add():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "viewer")
        display_name = request.form.get("display_name", "").strip()

        if not username or not email or not password:
            flash("Username, email, and password are required", "error")
            return render_template("user_form.html", user=None, categories=get_program_categories())
        if get_user_by_email(email):
            flash("Email already registered", "error")
            return render_template("user_form.html", user=None, categories=get_program_categories())
        if get_user_by_username(username):
            flash("Username already taken", "error")
            return render_template("user_form.html", user=None, categories=get_program_categories())

        add_user(username, email, password, role, display_name, 1)
        flash("User created and approved", "success")
        return redirect(url_for("user_list"))

    return render_template("user_form.html", user=None, categories=get_program_categories())


@app.route("/users/<int:uid>/edit", methods=["GET", "POST"])
@require_admin
def user_edit(uid):
    user = get_user(uid)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("user_list"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "viewer")
        display_name = request.form.get("display_name", "").strip()

        if not username or not email:
            flash("Username and email are required", "error")
            return render_template("user_form.html", user=user, categories=get_program_categories())

        other = get_user_by_email(email)
        if other and other["id"] != uid:
            flash("Email already in use", "error")
            return render_template("user_form.html", user=user, categories=get_program_categories())

        other = get_user_by_username(username)
        if other and other["id"] != uid:
            flash("Username already taken", "error")
            return render_template("user_form.html", user=user, categories=get_program_categories())

        update_user(uid, username, email, role, display_name)
        flash("User updated", "success")
        return redirect(url_for("user_list"))

    return render_template("user_form.html", user=user, categories=get_program_categories())


@app.route("/users/<int:uid>/password", methods=["GET", "POST"])
@require_admin
def user_password(uid):
    user = get_user(uid)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("user_list"))
    if request.method == "POST":
        new_pw = request.form.get("password", "")
        if not new_pw:
            flash("Password is required", "error")
            return render_template("admin_password.html", target=user, categories=get_program_categories())
        update_user_password(uid, new_pw)
        flash(f"Password reset for {user['display_name'] or user['username']}", "success")
        return redirect(url_for("user_list"))
    return render_template("admin_password.html", target=user, categories=get_program_categories())


@app.route("/users/<int:uid>/approve", methods=["POST"])
@require_admin
def user_approve(uid):
    user = get_user(uid)
    if not user:
        flash("User not found", "error")
    else:
        new_val = 0 if user["is_approved"] else 1
        set_user_approved(uid, new_val)
        flash(f"{user['display_name'] or user['username']} {'approved' if new_val else 'unapproved'}", "success")
    return redirect(url_for("user_list"))


@app.route("/users/<int:uid>/delete", methods=["POST"])
@require_admin
def user_delete(uid):
    user = get_user(uid)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("user_list"))
    try:
        delete_user(uid)
        flash(f"User {user['display_name'] or user['username']} deleted", "success")
    except ValueError as e:
        flash(str(e), "error")
    return redirect(url_for("user_list"))


@app.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    uid = session["user_id"]
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        user = get_user(uid)
        from werkzeug.security import check_password_hash
        if not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect", "error")
            return render_template("password.html", categories=get_program_categories())
        if new_pw != confirm:
            flash("New passwords do not match", "error")
            return render_template("password.html", categories=get_program_categories())
        if not new_pw:
            flash("New password is required", "error")
            return render_template("password.html", categories=get_program_categories())

        update_user_password(uid, new_pw)
        flash("Password changed successfully", "success")
        return redirect(url_for("dashboard"))

    return render_template("password.html", categories=get_program_categories())


# ─── Dashboard ──────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    counts = get_sub_program_counts()
    overdue_subs = get_overdue_sub_programs()
    active_subs = get_active_sub_programs()
    schedule = get_upcoming_schedule(20)
    categories = get_program_categories()
    due_today, due_this_week = get_due_reminders()

    # Counts for chart
    chart_counts = {
        "open": counts.get("open", 0),
        "in_progress": counts.get("in_progress", 0),
        "completed": counts.get("completed", 0),
        "on_hold_suspended": counts.get("on_hold_suspended", 0),
        "overdue": counts.get("overdue", 0),
    }

    return render_template(
        "dashboard.html",
        counts=counts,
        overdue_subs=overdue_subs,
        active_subs=active_subs,
        schedule=schedule,
        categories=categories,
        due_today=due_today,
        due_this_week=due_this_week,
        chart_counts=chart_counts,
    )


# ─── Programs ───────────────────────────────────────────

@app.route("/programs")
@login_required
def programs_landing():
    categories = get_program_categories()
    status_filter = request.args.get("status", "").strip()
    for c in categories:
        subs = get_all_sub_programs_with_status(category_id=c["id"])
        if status_filter:
            if status_filter == "overdue":
                subs = [s for s in subs if s["due_date"] and s["due_date"] < date.today().isoformat() and s["derived_status"] not in ("completed",)]
            elif status_filter == "on_hold":
                subs = [s for s in subs if s["derived_status"] in ("on_hold", "suspended")]
            else:
                subs = [s for s in subs if s["derived_status"] == status_filter]
        c["sub_count"] = len(subs)
        c["active_count"] = sum(1 for s in subs if s["derived_status"] != "completed")
    return render_template("programs.html", categories=categories, status=status_filter)


@app.route("/programs/<int:cat_id>")
@login_required
def program_category(cat_id):
    category = get_program_category(cat_id)
    if not category:
        flash("Category not found", "error")
        return redirect(url_for("programs_landing"))
    search = request.args.get("search", "")
    status_filter = request.args.get("status", "").strip()
    subs = get_all_sub_programs_with_status(category_id=cat_id, search=search)
    if status_filter:
        if status_filter == "overdue":
            subs = [s for s in subs if s["due_date"] and s["due_date"] < date.today().isoformat() and s["derived_status"] not in ("completed",)]
        elif status_filter == "on_hold":
            subs = [s for s in subs if s["derived_status"] in ("on_hold", "suspended")]
        else:
            subs = [s for s in subs if s["derived_status"] == status_filter]
    members = get_members()
    categories = get_program_categories()
    return render_template(
        "category.html",
        category=category, subs=subs,
        members=members, categories=categories,
        search=search, status=status_filter,
        recurring_types=RECURRING_TYPES,
        type_flags=TYPE_FLAGS,
    )


@app.route("/programs/sub/<int:sub_id>")
@login_required
def sub_program_detail(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    derived = get_sub_program_derived(sub_id)
    page = request.args.get("page", 1, type=int)
    tasks, total_tasks = get_tasks(sub_id, page=page, per_page=50)
    total_pages = max(1, (total_tasks + 49) // 50)
    team = get_sub_program_members(sub_id)
    members = get_members()
    categories = get_program_categories()
    return render_template(
        "sub_program.html",
        sub=sub, derived=derived, tasks=tasks,
        team=team, members=members, categories=categories,
        statuses=TASK_STATUSES, priorities=TASK_PRIORITIES,
        page=page, total_pages=total_pages, total_tasks=total_tasks,
    )


@app.route("/programs/add", methods=["GET", "POST"])
@require_write
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

        generate_recurring_instances(force=True)
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
@require_write
def sub_program_edit(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    if request.method == "POST":
        new_due = request.form.get("due_date") or None
        new_recurring = request.form.get("recurring_type", "none")

        # Block editing due_date or recurring_type on a base that has generated children
        if sub["recurring_type"] != "none" and sub["parent_id"] is None:
            child_count = count_generated_children(sub_id)
            if child_count > 0:
                due_changed = new_due != sub["due_date"]
                recurring_changed = new_recurring != sub["recurring_type"]
                if due_changed or recurring_changed:
                    child_dates = get_conn().execute(
                        "SELECT due_date FROM sub_programs WHERE parent_id=? ORDER BY due_date",
                        (sub_id,),
                    ).fetchall()
                    dates = ", ".join(r["due_date"] for r in child_dates[:3])
                    flash(f"Cannot change due date or recurrence type while generated instances exist (due {dates}…). Delete them first.", "error")
                    return redirect(url_for("sub_program_edit", sub_id=sub_id))

        update_sub_program(
            sub_id=sub_id,
            category_id=int(request.form["program_category_id"]),
            title=request.form["title"],
            description=request.form.get("description", ""),
            due_date=new_due,
            in_charge_id=request.form.get("in_charge_id", type=int),
            recurring_type=new_recurring,
            add_to_calendar=request.form.get("add_to_calendar", "0") == "1",
            type_flag=request.form.get("type_flag", "Program"),
            notes=request.form.get("notes", ""),
        )
        # Update members
        conn = None
        try:
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

        # Auto-run recurrence generation
        generate_recurring_instances(force=True)

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
@require_write
def sub_program_delete(sub_id):
    success = delete_sub_program(sub_id)
    if success:
        flash("Sub-program deleted", "success")
    else:
        flash("Cannot delete: some tasks are still Open or In-Progress", "error")
    return redirect(url_for("programs_landing"))


@app.route("/programs/sub/<int:sub_id>/note", methods=["POST"])
@require_write
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
@require_write
def task_add(sub_id):
    sub = get_sub_program(sub_id)
    if not sub:
        flash("Sub-program not found", "error")
        return redirect(url_for("programs_landing"))
    due = request.form.get("due_date") or None
    if due and sub["due_date"] and due > sub["due_date"]:
        flash(f"Task due date cannot be after sub-program due date ({sub['due_date']})", "error")
        return redirect(url_for("sub_program_detail", sub_id=sub_id))
    add_task(
        sub_program_id=sub_id,
        title=request.form["title"],
        due_date=due,
        assigned_to=request.form.get("assigned_to", type=int),
        priority=request.form.get("priority", "medium"),
    )
    flash("Task created", "success")
    return redirect(url_for("sub_program_detail", sub_id=sub_id))


@app.route("/tasks/<int:tid>", methods=["POST"])
@require_write
def task_update(tid):
    task = get_task(tid)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("programs_landing"))
    action = request.form.get("action")
    if action == "update":
        due = request.form.get("due_date") or None
        sub = get_sub_program(task["sub_program_id"])
        if due and sub and sub["due_date"] and due > sub["due_date"]:
            flash(f"Task due date cannot be after sub-program due date ({sub['due_date']})", "error")
            return redirect(url_for("sub_program_detail", sub_id=task["sub_program_id"]))
        update_task(
            task_id=tid,
            title=request.form["title"],
            due_date=due,
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
@require_write
def task_delete(tid):
    task = get_task(tid)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("programs_landing"))
    delete_task(tid)
    flash("Task deleted", "success")
    return redirect(url_for("sub_program_detail", sub_id=task["sub_program_id"]))


@app.route("/tasks/<int:tid>/duplicate", methods=["POST"])
@require_write
def task_duplicate(tid):
    task = get_task(tid)
    if not task:
        flash("Task not found", "error")
        return redirect(url_for("programs_landing"))
    new_due = None
    if task["due_date"]:
        new_due = (datetime.strptime(task["due_date"], "%Y-%m-%d") + timedelta(days=7)).isoformat()[:10]
    add_task(
        sub_program_id=task["sub_program_id"],
        title=task["title"] + " (copy)",
        due_date=new_due,
        assigned_to=task["assigned_to"],
        priority=task["priority"],
    )
    flash("Task duplicated", "success")
    return redirect(url_for("sub_program_detail", sub_id=task["sub_program_id"]))


@app.route("/tasks/<int:tid>/toggle", methods=["POST"])
@require_write
def task_toggle(tid):
    task = get_task(tid)
    if not task:
        if request.is_json:
            return jsonify({"error": "not found"}), 404
        flash("Task not found", "error")
        return redirect(url_for("programs_landing"))
    new_status = "open" if task["status"] == "completed" else "completed"
    update_task_status(tid, new_status)
    if request.is_json:
        return jsonify({"status": new_status})
    flash(f"Task marked {new_status}", "success")
    return redirect(url_for("sub_program_detail", sub_id=task["sub_program_id"]))


# ─── Calendar ───────────────────────────────────────────

@app.route("/calendar")
@login_required
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
@login_required
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
@require_write
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

        generate_recurring_instances(force=True)
        flash("Event added", "success")
        rt = request.form.get("recurring_type", "none")
        if rt != "none":
            next_dates = get_next_recurrence_dates(start_date, rt, 3)
            if next_dates:
                flash(f"Recurring ({rt}): next instances on " + ", ".join(next_dates), "success")
        return redirect(url_for("calendar_view"))

    subs = get_all_sub_programs_with_status()
    members = get_members()
    return render_template(
        "event_form.html", event=None,
        subs=subs, members=members,
        recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
    )


@app.route("/events/<int:eid>/edit", methods=["POST"])
@require_write
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
    generate_recurring_instances(force=True)
    flash("Event updated", "success")

    rt = request.form.get("recurring_type", event["recurring_type"])
    if rt != "none":
        next_dates = get_next_recurrence_dates(request.form["start_date"], rt, 3)
        if next_dates:
            flash(f"Recurring ({rt}): next instances on " + ", ".join(next_dates), "success")
    return redirect(url_for("calendar_view"))


@app.route("/events/<int:eid>/delete", methods=["POST"])
@require_write
def event_delete(eid):
    delete_event(eid)
    flash("Event deleted", "success")
    return redirect(url_for("calendar_view"))


# ─── Program Categories ─────────────────────────────────

@app.route("/programs/category/add", methods=["GET", "POST"])
@require_write
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
@require_write
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
@require_write
def category_delete(cat_id):
    delete_program_category(cat_id)
    flash("Category deleted", "success")
    return redirect(url_for("programs_landing"))


# ─── Members / Directory ─────────────────────────────────

@app.route("/members")
@login_required
def member_list():
    members = get_members()
    categories = get_program_categories()
    return render_template("members.html", members=members, categories=categories)


@app.route("/members/add", methods=["GET", "POST"])
@require_write
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
@require_write
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
@require_write
def member_delete(mid):
    member = get_member(mid)
    if not member:
        flash("Member not found", "error")
        return redirect(url_for("member_list"))
    # Count orphaned refs for warning
    conn = get_conn()
    sp_count = conn.execute("SELECT COUNT(*) AS c FROM sub_programs WHERE in_charge_id=?", (mid,)).fetchone()["c"]
    task_count = conn.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_to=?", (mid,)).fetchone()["c"]
    conn.close()
    parts = []
    if sp_count:
        parts.append(f"{sp_count} sub-program(s)")
    if task_count:
        parts.append(f"{task_count} task(s)")
    delete_member(mid)
    msg = "Member deleted"
    if parts:
        msg += " — references cleared from " + ", ".join(parts)
    flash(msg, "success")
    return redirect(url_for("member_list"))


# ─── Import ──────────────────────────────────────────────

@app.route("/import", methods=["GET", "POST"])
@require_write
def import_data():
    categories = get_program_categories()
    if request.method == "POST":
        entity = request.form.get("entity")
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Please select a file", "error")
            return render_template("import.html", categories=categories, entity=entity)

        content = file.read().decode("utf-8-sig").splitlines()
        reader = csv.DictReader(content)
        rows = list(reader)
        if not rows:
            flash("File is empty or has no valid rows", "error")
            return render_template("import.html", categories=categories, entity=entity)

        imported = 0
        errors = 0

        if entity == "members":
            for r in rows:
                try:
                    add_member(
                        name=r.get("name", r.get("Name", "")).strip(),
                        designation=r.get("designation", r.get("Designation", "")).strip(),
                        phone=r.get("phone", r.get("Phone", "")).strip(),
                        email=r.get("email", r.get("Email", "")).strip(),
                    )
                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "events":
            for r in rows:
                try:
                    add_event(
                        title=r.get("title", r.get("Title", "")).strip(),
                        sub_program_id=None,
                        recurring_type=r.get("recurring_type", r.get("Recurring", "none")).strip(),
                        type_flag=r.get("type_flag", r.get("Type", "Event")).strip(),
                        start_date=r.get("start_date", r.get("Date", "")).strip(),
                        notes=r.get("notes", r.get("Notes", "")).strip(),
                    )
                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "tasks":
            for r in rows:
                try:
                    add_task(
                        sub_program_id=1,
                        title=r.get("title", r.get("Title", "")).strip(),
                        due_date=r.get("due_date", r.get("Due", "")).strip() or None,
                        assigned_to=None,
                        priority=r.get("priority", r.get("Priority", "medium")).strip(),
                    )
                    imported += 1
                except Exception:
                    errors += 1

        else:
            flash("Unknown entity type", "error")
            return render_template("import.html", categories=categories, entity=entity)

        msg = f"Imported {imported} {entity}"
        if errors:
            msg += f" ({errors} errors)"
        flash(msg, "success")
        return redirect(url_for("dashboard"))

    return render_template("import.html", categories=categories, entity=None)


# ─── CSV Export ──────────────────────────────────────────

@app.route("/export/tasks")
@login_required
def export_tasks_csv():
    import io
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.id, t.title, t.status, t.priority, t.due_date,
               m.name AS assigned_to, sp.title AS sub_program
        FROM tasks t
        LEFT JOIN members m ON t.assigned_to = m.id
        LEFT JOIN sub_programs sp ON t.sub_program_id = sp.id
        ORDER BY t.id
    """).fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["ID", "Title", "Status", "Priority", "Due Date", "Assigned To", "Sub-Program"])
    for r in rows:
        w.writerow([r["id"], r["title"], r["status"], r["priority"], r["due_date"], r["assigned_to"], r["sub_program"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=tasks.csv"}


@app.route("/export/events")
@login_required
def export_events_csv():
    import io
    conn = get_conn()
    rows = conn.execute("""
        SELECT e.id, e.title, e.type_flag, e.start_date, e.recurring_type,
               sp.title AS sub_program
        FROM events e
        LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
        ORDER BY e.start_date
    """).fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["ID", "Title", "Type", "Date", "Recurring", "Sub-Program"])
    for r in rows:
        w.writerow([r["id"], r["title"], r["type_flag"], r["start_date"], r["recurring_type"], r["sub_program"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=events.csv"}


@app.route("/export/members")
@login_required
def export_members_csv():
    import io
    conn = get_conn()
    rows = conn.execute("SELECT id, name, designation, phone, email FROM members ORDER BY name").fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["ID", "Name", "Designation", "Phone", "Email"])
    for r in rows:
        w.writerow([r["id"], r["name"], r["designation"], r["phone"], r["email"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=members.csv"}


# ─── Bootstrap ───────────────────────────────────────────

is_fly = os.environ.get("FLY_APP_NAME") is not None


@app.errorhandler(404)
def not_found(e):
    categories = get_program_categories()
    return render_template("404.html", categories=categories), 404

# Auto-seed on first run (runs at import for gunicorn compatibility).
# Skip when TESTING env is set (test_all.py sets this).
if not os.environ.get("CHMS_TESTING"):
    conn = get_conn()
    needs_seed = conn.execute("SELECT COUNT(*) AS c FROM members").fetchone()["c"] == 0
    if needs_seed:
        conn.close()
        print("First run — seeding database...")
        import seed
        seed.seed()
        print("Database seeded successfully.")
    else:
        conn.close()

    # Always ensure admin user exists (covers existing DBs pre-user-management)
    from models import get_user_by_email, add_user
    admin_pw = os.environ.get("CHMS_ADMIN_PASSWORD", "qazcde@123")
    if not get_user_by_email("admin@livingway.church"):
        add_user("admin", "admin@livingway.church", admin_pw, "admin", "Administrator", 1)
        print("Created admin user (admin@livingway.church)")
    else:
        from werkzeug.security import generate_password_hash
        conn2 = get_conn()
        conn2.execute("UPDATE users SET password_hash=?, is_approved=1 WHERE email='admin@livingway.church'",
                      (generate_password_hash(admin_pw),))
        conn2.commit()
        conn2.close()

if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN") and not is_fly:
        Timer(1.5, lambda: webbrowser.open_new("http://127.0.0.1:5000/")).start()
    port = int(os.environ.get("PORT", 5000))
    print(f"ChMS(prototype) starting on 0.0.0.0:{port}")
    print(f"Data directory: {get_data_dir()}")
    print("Close terminal or press Ctrl+C to stop.")
    app.run(host="0.0.0.0", port=port, debug=False)
