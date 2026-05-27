import os, csv, json, io, zipfile
from datetime import datetime, date, timedelta
from calendar import monthcalendar

from flask import (
    Flask, render_template, request, redirect,
    url_for, jsonify, flash, session
)

from werkzeug.security import check_password_hash, generate_password_hash

from models import (
    generate_recurring_instances,
    count_generated_children,
    get_members, get_member, add_member, update_member, delete_member,
    get_program_categories, get_program_category,
    add_program_category, update_program_category, delete_program_category,
    get_sub_program, add_sub_program, update_sub_program, delete_sub_program,
    get_sub_program_members, add_sub_program_member, remove_sub_program_member,
    get_all_sub_programs_with_status, get_sub_program_counts,
    get_sub_program_derived, get_linkable_sub_programs,
    get_overdue_sub_programs, get_active_sub_programs,
    get_tasks, get_task, add_task, update_task, update_task_status, delete_task,
    get_task_updates as _get_task_updates, add_task_update,
    get_events, get_event, add_event, update_event, delete_event,
    get_calendar_entries, get_calendar_entries_from_date,
    get_upcoming_schedule, get_due_reminders,
    get_next_recurrence_dates,
    get_users, get_user, get_user_by_email, get_user_by_username,
    add_user, update_user, update_user_password, set_user_approved, delete_user,
    verify_user,
    TASK_STATUSES, TASK_PRIORITIES, RECURRING_TYPES, TYPE_FLAGS,
    get_conn, init_db,
)

app = Flask(__name__)
app.secret_key = os.environ.get("CHMS_SECRET_KEY", "chms-secret-key")
app.config["APP_VERSION"] = os.environ.get("APP_VERSION", "v.dev")

LAST_RECURRENCE_CHECK = None


@app.template_global()
def today():
    return date.today().isoformat()


@app.template_global()
def app_version():
    return app.config["APP_VERSION"]


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
    categories = get_program_categories()
    return dict(current_user=user, categories=categories)


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
    return render_template("users.html", users=users)


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
            return render_template("user_form.html", user=None)
        if get_user_by_email(email):
            flash("Email already registered", "error")
            return render_template("user_form.html", user=None)
        if get_user_by_username(username):
            flash("Username already taken", "error")
            return render_template("user_form.html", user=None)

        add_user(username, email, password, role, display_name, 1)
        flash("User created and approved", "success")
        return redirect(url_for("user_list"))

    return render_template("user_form.html", user=None)


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
            return render_template("user_form.html", user=user)

        other = get_user_by_email(email)
        if other and other["id"] != uid:
            flash("Email already in use", "error")
            return render_template("user_form.html", user=user)

        other = get_user_by_username(username)
        if other and other["id"] != uid:
            flash("Username already taken", "error")
            return render_template("user_form.html", user=user)

        update_user(uid, username, email, role, display_name)
        flash("User updated", "success")
        return redirect(url_for("user_list"))

    return render_template("user_form.html", user=user)


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
            return render_template("admin_password.html", target=user)
        update_user_password(uid, new_pw)
        flash(f"Password reset for {user['display_name'] or user['username']}", "success")
        return redirect(url_for("user_list"))
    return render_template("admin_password.html", target=user)


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
        if not check_password_hash(user["password_hash"], current):
            flash("Current password is incorrect", "error")
            return render_template("password.html")
        if new_pw != confirm:
            flash("New passwords do not match", "error")
            return render_template("password.html")
        if not new_pw:
            flash("New password is required", "error")
            return render_template("password.html")

        update_user_password(uid, new_pw)
        flash("Password changed successfully", "success")
        return redirect(url_for("dashboard"))

    return render_template("password.html")


# ─── Dashboard ──────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    counts = get_sub_program_counts()
    overdue_subs = get_overdue_sub_programs()
    active_subs = get_active_sub_programs()
    schedule = get_upcoming_schedule(20)
    due_today, due_this_week = get_due_reminders()

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
        due_today=due_today,
        due_this_week=due_this_week,
        chart_counts=chart_counts,
    )


@app.route("/dashboard/data")
@login_required
def dashboard_data():
    counts = get_sub_program_counts()
    overdue_subs = get_overdue_sub_programs()
    active_subs = get_active_sub_programs()
    schedule = get_upcoming_schedule(20)
    due_today, due_this_week = get_due_reminders()

    return jsonify({
        "counts": counts,
        "overdue_subs": overdue_subs,
        "active_subs": active_subs,
        "schedule": schedule,
        "due_today": due_today,
        "due_this_week": due_this_week,
        "chart_counts": {
            "open": counts.get("open", 0),
            "in_progress": counts.get("in_progress", 0),
            "completed": counts.get("completed", 0),
            "on_hold_suspended": counts.get("on_hold_suspended", 0),
            "overdue": counts.get("overdue", 0),
        },
    })


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
    return render_template(
        "category.html",
        category=category, subs=subs,
        members=members,
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
    return render_template(
        "sub_program.html",
        sub=sub, derived=derived, tasks=tasks,
        team=team, members=members,
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
            recurring_by=request.form.get("recurring_by", "date"),
            recurring_weekday=request.form.get("recurring_weekday", type=int),
            recurring_ordinal=request.form.get("recurring_ordinal", type=int),
        )

        member_ids = request.form.getlist("member_ids")
        for mid in member_ids:
            add_sub_program_member(sub_id, int(mid))

        generate_recurring_instances(force=True)
        flash("Sub-program created", "success")
        return redirect(url_for("program_category", cat_id=request.form["program_category_id"]))
    members = get_members()
    sub_program_type_flags = [f for f in TYPE_FLAGS if f != "Service"]
    return render_template(
        "sub_program_form.html", sub=None,
        members=members,
        recurring_types=RECURRING_TYPES, type_flags=sub_program_type_flags,
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
                        "SELECT due_date FROM sub_programs WHERE parent_id=%s ORDER BY due_date",
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
            recurring_by=request.form.get("recurring_by", "date"),
            recurring_weekday=request.form.get("recurring_weekday", type=int),
            recurring_ordinal=request.form.get("recurring_ordinal", type=int),
        )
        # Update members
        conn = None
        try:
            conn = get_conn()
            conn.execute("DELETE FROM sub_program_members WHERE sub_program_id=%s", (sub_id,))
            member_ids = request.form.getlist("member_ids")
            for mid in member_ids:
                conn.execute(
                    "INSERT INTO sub_program_members (sub_program_id, member_id) VALUES (%s,%s)",
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
    sub_program_type_flags = [f for f in TYPE_FLAGS if f != "Service"]
    return render_template(
        "sub_program_form.html", sub=sub, team_ids=team_ids,
        members=members,
        recurring_types=RECURRING_TYPES, type_flags=sub_program_type_flags,
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
        conn.execute("UPDATE sub_programs SET notes=%s, updated_at=TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS') WHERE id=%s",
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
    next_m = month + 1 if month < 12 else 1
    next_y = year + 1 if month == 12 else year
    later_entries = get_calendar_entries_from_date(next_y, next_m)
    month_events = get_events(year=year, month=month)
    members = get_members()
    event_type_flags = [f for f in TYPE_FLAGS if f != "Program"]

    return render_template(
        "calendar.html",
        cal=cal, day_names=day_names,
        year=year, month=month,
        next_month=next_month, next_year=next_year,
        prev_month=prev_month, prev_year=prev_year,
        today=today_dt.isoformat(),
        entries_by_date=entries_by_date,
        month_entries=month_entries,
        later_entries=later_entries,
        month_events=month_events,
        members=members,
        months=[
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        recurring_types=RECURRING_TYPES, type_flags=TYPE_FLAGS,
        event_type_flags=event_type_flags,
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
        recurring_by = request.form.get("recurring_by", "date")
        recurring_weekday = request.form.get("recurring_weekday", type=int)
        recurring_ordinal = request.form.get("recurring_ordinal", type=int)

        if sub_id:
            sp = get_sub_program(sub_id)
            if sp and sp["due_date"] and sp["due_date"] < start_date:
                flash("Event date cannot be after the linked sub-program's due date", "error")
                subs = get_linkable_sub_programs()
                members = get_members()
                event_type_flags = [f for f in TYPE_FLAGS if f != "Program"]
                return render_template(
                    "event_form.html", event=None,
                    subs=subs, members=members,
                    recurring_types=RECURRING_TYPES, type_flags=event_type_flags,
                )

        rt = request.form.get("recurring_type", "none")
        expiry = request.form.get("expiry_date")
        if rt != "none" and not expiry:
            flash("Recurring Expiry Date is required for recurring events", "error")
            subs = get_linkable_sub_programs()
            members = get_members()
            event_type_flags = [f for f in TYPE_FLAGS if f != "Program"]
            return render_template(
                "event_form.html", event=None,
                subs=subs, members=members,
                recurring_types=RECURRING_TYPES, type_flags=event_type_flags,
            )

        event_id = add_event(
            title=request.form["title"],
            sub_program_id=sub_id,
            recurring_type=request.form.get("recurring_type", "none"),
            type_flag=request.form.get("type_flag", "Event"),
            start_date=start_date,
            notes=request.form.get("notes", ""),
            expiry_date=expiry or None,
            recurring_by=recurring_by,
            recurring_weekday=recurring_weekday,
            recurring_ordinal=recurring_ordinal,
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
            expiry = request.form.get("expiry_date") or None
            next_dates = get_next_recurrence_dates(
                start_date, rt, 3, expiry,
                recurring_by=recurring_by,
                recurring_weekday=recurring_weekday,
                recurring_ordinal=recurring_ordinal,
            )
            if next_dates:
                flash(f"Recurring ({rt}): next instances on " + ", ".join(next_dates), "success")
        return redirect(url_for("calendar_view"))

    subs = get_linkable_sub_programs()
    members = get_members()
    event_type_flags = [f for f in TYPE_FLAGS if f != "Program"]
    return render_template(
        "event_form.html", event=None,
        subs=subs, members=members,
        recurring_types=RECURRING_TYPES, type_flags=event_type_flags,
    )


@app.route("/events/<int:eid>/edit", methods=["GET", "POST"])
@require_write
def event_edit(eid):
    event = get_event(eid)
    if not event:
        flash("Event not found", "error")
        return redirect(url_for("calendar_view"))

    if request.method == "GET":
        subs = get_linkable_sub_programs()
        members = get_members()
        event_type_flags = [f for f in TYPE_FLAGS if f != "Program"]
        return render_template(
            "event_form.html", event=event,
            subs=subs, members=members,
            recurring_types=RECURRING_TYPES, type_flags=event_type_flags,
        )

    recurring_by = request.form.get("recurring_by", event.get("recurring_by", "date"))
    recurring_weekday = request.form.get("recurring_weekday", type=int)
    recurring_ordinal = request.form.get("recurring_ordinal", type=int)

    rt = request.form.get("recurring_type", "none")
    expiry = request.form.get("expiry_date")
    if rt != "none" and not expiry:
        flash("Recurring Expiry Date is required for recurring events", "error")
        return redirect(url_for("event_edit", eid=eid))

    update_event(
        event_id=eid,
        title=request.form["title"],
        sub_program_id=request.form.get("sub_program_id", type=int),
        recurring_type=request.form.get("recurring_type", "none"),
        type_flag=request.form.get("type_flag", "Event"),
        start_date=request.form["start_date"],
        notes=request.form.get("notes", ""),
        expiry_date=expiry or None,
        recurring_by=recurring_by,
        recurring_weekday=recurring_weekday,
        recurring_ordinal=recurring_ordinal,
    )
    generate_recurring_instances(force=True)
    flash("Event updated", "success")

    if rt != "none":
        next_dates = get_next_recurrence_dates(
            request.form["start_date"], rt, 3, expiry,
            recurring_by=recurring_by,
            recurring_weekday=recurring_weekday,
            recurring_ordinal=recurring_ordinal,
        )
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


@app.route("/programs/category/<int:cat_id>/edit", methods=["GET", "POST"])
@require_write
def category_edit(cat_id):
    cat = get_program_category(cat_id)
    if not cat:
        flash("Category not found", "error")
        return redirect(url_for("programs_landing"))
    if request.method == "GET":
        conn = get_conn()
        sub_count = conn.execute(
            "SELECT COUNT(*) AS c FROM sub_programs WHERE program_category_id=%s", (cat_id,)
        ).fetchone()["c"]
        conn.close()
        return render_template("category_form.html", category=cat, sub_count=sub_count)
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
    conn = get_conn()
    sub_count = conn.execute(
        "SELECT COUNT(*) AS c FROM sub_programs WHERE program_category_id=%s", (cat_id,)
    ).fetchone()["c"]
    conn.close()
    if sub_count > 0:
        flash("Cannot delete category with existing sub-programs", "error")
        return redirect(url_for("category_edit", cat_id=cat_id))
    delete_program_category(cat_id)
    flash("Category deleted", "success")
    return redirect(url_for("programs_landing"))


# ─── Members / Directory ─────────────────────────────────

@app.route("/members")
@login_required
def member_list():
    members = get_members()
    return render_template("members.html", members=members)


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
    conn = get_conn()
    today = date.today().isoformat()
    # Check open tasks
    open_tasks = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE assigned_to=%s AND status NOT IN ('completed','on_hold','suspended')",
        (mid,),
    ).fetchone()["c"]
    # Check non-completed sub-programs where member is in charge
    active_subs = conn.execute(
        "SELECT COUNT(*) AS c FROM sub_programs WHERE in_charge_id=%s AND (due_date IS NULL OR due_date >= %s)",
        (mid, today),
    ).fetchone()["c"]
    # Check non-completed sub-programs where member is on the team
    team_subs = conn.execute("""
        SELECT COUNT(*) AS c FROM sub_program_members spm
        JOIN sub_programs sp ON spm.sub_program_id = sp.id
        WHERE spm.member_id=%s AND sp.due_date IS NOT NULL AND sp.due_date >= %s
    """, (mid, today)).fetchone()["c"]
    # Check future events linked to sub-programs where member is involved
    future_events = conn.execute("""
        SELECT COUNT(*) AS c FROM events e
        JOIN sub_programs sp ON e.sub_program_id = sp.id
        WHERE e.start_date >= %s AND (sp.in_charge_id=%s OR sp.id IN (
            SELECT sub_program_id FROM sub_program_members WHERE member_id=%s
        ))
    """, (today, mid, mid)).fetchone()["c"]
    conn.close()

    blocks = []
    if open_tasks:
        blocks.append(f"{open_tasks} open task(s)")
    if active_subs:
        blocks.append(f"{active_subs} active sub-program(s) as in-charge")
    if team_subs:
        blocks.append(f"{team_subs} upcoming sub-program(s) as team member")
    if future_events:
        blocks.append(f"{future_events} future event(s)")
    if blocks:
        flash("Cannot delete: member is assigned to " + ", ".join(blocks), "error")
        return redirect(url_for("member_list"))
    delete_member(mid)
    flash("Member deleted", "success")
    return redirect(url_for("member_list"))


# ─── Import ──────────────────────────────────────────────

@app.route("/import", methods=["GET", "POST"])
@require_write
def import_data():
    if request.method == "POST":
        entity = request.form.get("entity")
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Please select a file", "error")
            return render_template("import.html", entity=entity)

        imported = 0
        errors = 0

        if file.filename.lower().endswith(".zip"):
            return _import_zip(file)

        content = file.read().decode("utf-8-sig").splitlines()
        reader = csv.DictReader(content)
        rows = list(reader)
        if not rows:
            flash("File is empty or has no valid rows", "error")
            return render_template("import.html", entity=entity)

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

        elif entity == "programs":
            for r in rows:
                try:
                    name = r.get("name", r.get("Name", "")).strip()
                    if not name:
                        errors += 1
                        continue
                    add_program_category(
                        name=name,
                        description=r.get("description", r.get("Description", "")).strip(),
                        sort_order=int(r.get("sort_order", r.get("Sort Order", 0)) or 0),
                    )
                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "sub_programs":
            all_members = {m["id"]: m for m in get_members()}
            cat_lookup = {c["name"].strip().lower(): c["id"] for c in get_program_categories()}
            member_name_lookup = {m["name"].strip().lower(): m["id"] for m in get_members()}
            for r in rows:
                try:
                    title = r.get("title", r.get("Title", "")).strip()
                    cat_name = r.get("program_category", r.get("Category", "")).strip()
                    if not title or not cat_name:
                        errors += 1
                        continue
                    cat_id = cat_lookup.get(cat_name.strip().lower())
                    if cat_id is None:
                        cat_id = add_program_category(cat_name, "", 99)
                        cat_lookup[cat_name.strip().lower()] = cat_id

                    in_charge_name = r.get("in_charge", "").strip()
                    in_charge_id = member_name_lookup.get(in_charge_name.lower()) if in_charge_name else None

                    sp_id = add_sub_program(
                        category_id=cat_id,
                        title=title,
                        description=r.get("description", r.get("Description", "")).strip(),
                        due_date=r.get("due_date", r.get("Due Date", "")) or None,
                        in_charge_id=in_charge_id,
                        recurring_type=r.get("recurring_type", "none").strip(),
                        add_to_calendar=r.get("add_to_calendar", "0").strip() in ("1", "yes", "true"),
                        type_flag=r.get("type_flag", "Program").strip(),
                        notes=r.get("notes", r.get("Notes", "")).strip(),
                    )

                    team_str = r.get("team_members", r.get("Team Members", "")).strip()
                    if team_str:
                        for mid_str in team_str.split(","):
                            mid_str = mid_str.strip()
                            if mid_str and mid_str.isdigit():
                                mid = int(mid_str)
                                if mid in all_members:
                                    add_sub_program_member(sp_id, mid)

                    for i in range(1, 11):
                        t_title = r.get(f"task_{i}_title", r.get(f"Task {i} Title", "")).strip()
                        if not t_title:
                            continue
                        add_task(
                            sub_program_id=sp_id,
                            title=t_title,
                            due_date=r.get(f"task_{i}_due_date", r.get(f"Task {i} Due Date", "")) or None,
                            assigned_to=int(r.get(f"task_{i}_assigned_to", r.get(f"Task {i} Assigned To", "0")) or 0) or None,
                            priority=r.get(f"task_{i}_priority", r.get(f"Task {i} Priority", "medium")).strip(),
                        )

                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "tasks":
            sp_lookup = {}
            for r in rows:
                try:
                    sp_title = r.get("sub_program", r.get("Sub Program", "")).strip()
                    if sp_title not in sp_lookup:
                        all_sp = get_all_sub_programs_with_status()
                        sp_lookup = {s["title"].strip().lower(): s["id"] for s in all_sp}
                    sp_id = sp_lookup.get(sp_title.lower())
                    if not sp_id:
                        errors += 1
                        continue
                    title = r.get("title", r.get("Title", "")).strip()
                    if not title:
                        errors += 1
                        continue
                    assigned_to = int(r.get("assigned_to", r.get("Assigned To", "0")) or 0) or None
                    add_task(
                        sub_program_id=sp_id,
                        title=title,
                        due_date=r.get("due_date", r.get("Due Date", "")) or None,
                        assigned_to=assigned_to,
                        priority=r.get("priority", r.get("Priority", "medium")).strip(),
                    )
                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "events":
            sp_lookup = {}
            for r in rows:
                try:
                    title = r.get("title", r.get("Title", "")).strip()
                    start_date = r.get("start_date", r.get("Date", "")).strip()
                    type_flag = r.get("type_flag", r.get("Type", "Event")).strip()
                    if not title or not start_date or not type_flag:
                        errors += 1
                        continue

                    sp_title = r.get("sub_program", r.get("Sub Program", "")).strip()
                    sp_id = None
                    if sp_title:
                        if sp_title not in sp_lookup:
                            all_sp = get_all_sub_programs_with_status()
                            sp_lookup = {s["title"].strip().lower(): s["id"] for s in all_sp}
                        sp_id = sp_lookup.get(sp_title.lower())

                    event_id = add_event(
                        title=title,
                        sub_program_id=sp_id,
                        recurring_type=r.get("recurring_type", r.get("Recurring", "none")).strip(),
                        type_flag=type_flag,
                        start_date=start_date,
                        notes=r.get("notes", r.get("Notes", "")).strip(),
                    )

                    assignee = int(r.get("assignee", r.get("Assignee", "0")) or 0) or None
                    if sp_id and assignee:
                        add_task(
                            sub_program_id=sp_id,
                            title=title,
                            due_date=start_date,
                            assigned_to=assignee,
                            priority="medium",
                        )

                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "users":
            for r in rows:
                try:
                    username = r.get("username", r.get("Username", "")).strip()
                    email = r.get("email", r.get("Email", "")).strip().lower()
                    pw_hash = r.get("password_hash", "").strip()
                    role = r.get("role", r.get("Role", "viewer")).strip()
                    display_name = r.get("display_name", r.get("Display Name", "")).strip()
                    is_approved = int(r.get("is_approved", r.get("Is Approved", "1")) or 1)
                    if not username or not email or not pw_hash or not role:
                        errors += 1
                        continue
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO users (username, email, password_hash, role, display_name, is_approved)"
                        " VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING",
                        (username, email, pw_hash, role, display_name, is_approved),
                    )
                    conn.commit()
                    conn.close()
                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "app_config":
            for r in rows:
                try:
                    key = r.get("key", r.get("Key", "")).strip()
                    value = r.get("value", r.get("Value", "")).strip()
                    if not key:
                        errors += 1
                        continue
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO app_config (key, value) VALUES (%s,%s)"
                        " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                        (key, value),
                    )
                    conn.commit()
                    conn.close()
                    imported += 1
                except Exception:
                    errors += 1

        elif entity == "sub_program_members":
            sp_names = {s["title"].strip().lower(): s["id"] for s in get_all_sub_programs_with_status()}
            member_names = {m["name"].strip().lower(): m["id"] for m in get_members()}
            for r in rows:
                try:
                    sp_title = r.get("sub_program_title", r.get("Sub Program Title", "")).strip()
                    member_name = r.get("member_name", r.get("Member Name", "")).strip()
                    sp_id = sp_names.get(sp_title.lower())
                    member_id = member_names.get(member_name.lower())
                    if sp_id and member_id:
                        add_sub_program_member(sp_id, member_id)
                        imported += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        elif entity == "task_updates":
            sp_names = {s["title"].strip().lower(): s["id"] for s in get_all_sub_programs_with_status()}
            for r in rows:
                try:
                    sp_title = r.get("sub_program_title", r.get("Sub Program Title", "")).strip()
                    task_title = r.get("task_title", r.get("Task Title", "")).strip()
                    note = r.get("note", r.get("Note", "")).strip()
                    if not sp_title or not task_title or not note:
                        errors += 1
                        continue
                    sp_id = sp_names.get(sp_title.lower())
                    if not sp_id:
                        errors += 1
                        continue
                    tasks, _ = get_tasks(sp_id, page=1, per_page=500)
                    task_id = None
                    for t in tasks:
                        if t["title"].strip().lower() == task_title.lower():
                            task_id = t["id"]
                            break
                    if task_id:
                        add_task_update(task_id, note)
                        imported += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        else:
            flash("Unknown entity type", "error")
            return render_template("import.html", entity=entity)

        msg = f"Imported {imported} {entity}"
        if errors:
            msg += f" ({errors} errors)"
        flash(msg, "success")
        return redirect(url_for("dashboard"))

    return render_template("import.html", entity=None)


def _import_zip(file):
    imported = 0
    errors = 0
    zip_data = file.read()
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        member_names = [n for n in zf.namelist() if n.endswith(".csv")]
        order = ["users", "app_config", "members", "program_categories",
                 "sub_programs", "sub_program_members", "tasks", "task_updates", "events"]
        for name in order:
            csv_name = f"{name}.csv"
            if csv_name not in member_names:
                continue
            content = zf.read(csv_name).decode("utf-8-sig").splitlines()
            reader = csv.DictReader(content)
            rows = list(reader)
            if not rows:
                continue
            for r in rows:
                try:
                    if name == "users":
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO users (username, email, password_hash, role, display_name, is_approved)"
                            " VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (email) DO NOTHING",
                            (r.get("username","").strip(), r.get("email","").strip().lower(),
                             r.get("password_hash","").strip(),
                             r.get("role","viewer").strip(),
                             r.get("display_name","").strip(),
                             int(r.get("is_approved","1") or 1)),
                        )
                        conn.commit()
                        conn.close()
                        imported += 1
                    elif name == "app_config":
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO app_config (key, value) VALUES (%s,%s)"
                            " ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
                            (r.get("key","").strip(), r.get("value","").strip()),
                        )
                        conn.commit()
                        conn.close()
                        imported += 1
                    elif name == "members":
                        add_member(
                            name=r.get("name", r.get("Name", "")).strip(),
                            designation=r.get("designation", r.get("Designation", "")).strip(),
                            phone=r.get("phone", r.get("Phone", "")).strip(),
                            email=r.get("email", r.get("Email", "")).strip(),
                        )
                        imported += 1
                    elif name == "program_categories":
                        add_program_category(
                            name=r.get("name", r.get("Name", "")).strip(),
                            description=r.get("description", r.get("Description", "")).strip(),
                            sort_order=int(r.get("sort_order", r.get("Sort Order", 0)) or 0),
                        )
                        imported += 1
                    elif name == "sub_programs":
                        _import_zip_sub_program(r)
                        imported += 1
                    elif name == "sub_program_members":
                        sp_names = {s["title"].strip().lower(): s["id"]
                                    for s in get_all_sub_programs_with_status()}
                        member_names = {m["name"].strip().lower(): m["id"] for m in get_members()}
                        sp_id = sp_names.get(r.get("sub_program_title","").strip().lower())
                        member_id = member_names.get(r.get("member_name","").strip().lower())
                        if sp_id and member_id:
                            add_sub_program_member(sp_id, member_id)
                            imported += 1
                        else:
                            errors += 1
                    elif name == "tasks":
                        sp_lookup = {s["title"].strip().lower(): s["id"]
                                     for s in get_all_sub_programs_with_status()}
                        sp_id = sp_lookup.get(r.get("sub_program","").strip().lower())
                        if not sp_id:
                            errors += 1
                            continue
                        add_task(
                            sub_program_id=sp_id,
                            title=r.get("title", r.get("Title", "")).strip(),
                            due_date=r.get("due_date", r.get("Due Date", "")) or None,
                            assigned_to=int(r.get("assigned_to","0") or 0) or None,
                            priority=r.get("priority", "medium").strip(),
                        )
                        imported += 1
                    elif name == "task_updates":
                        sp_names = {s["title"].strip().lower(): s["id"]
                                    for s in get_all_sub_programs_with_status()}
                        sp_id = sp_names.get(r.get("sub_program_title","").strip().lower())
                        if not sp_id:
                            errors += 1
                            continue
                        tasks, _ = get_tasks(sp_id, page=1, per_page=500)
                        tid = None
                        for t in tasks:
                            if t["title"].strip().lower() == r.get("task_title","").strip().lower():
                                tid = t["id"]
                                break
                        if tid:
                            add_task_update(tid, r.get("note","").strip())
                            imported += 1
                        else:
                            errors += 1
                    elif name == "events":
                        sp_lookup = {s["title"].strip().lower(): s["id"]
                                     for s in get_all_sub_programs_with_status()}
                        add_event(
                            title=r.get("title", r.get("Title", "")).strip(),
                            sub_program_id=sp_lookup.get(r.get("sub_program","").strip().lower()),
                            recurring_type=r.get("recurring_type", "none").strip(),
                            type_flag=r.get("type_flag", "Event").strip(),
                            start_date=r.get("start_date", r.get("Date", "")).strip(),
                            notes=r.get("notes", r.get("Notes", "")).strip(),
                        )
                        imported += 1
                except Exception:
                    errors += 1

    msg = f"Restored {imported} records from backup"
    if errors:
        msg += f" ({errors} errors)"
    flash(msg, "success")
    return redirect(url_for("dashboard"))


def _import_zip_sub_program(r):
    cat_lookup = {c["name"].strip().lower(): c["id"] for c in get_program_categories()}
    member_name_lookup = {m["name"].strip().lower(): m["id"] for m in get_members()}
    cat_name = r.get("program_category", r.get("Category", "")).strip()
    cat_id = cat_lookup.get(cat_name.lower())
    if cat_id is None:
        cat_id = add_program_category(cat_name, "", 99)
    in_charge_name = r.get("in_charge", "").strip()
    in_charge_id = member_name_lookup.get(in_charge_name.lower()) if in_charge_name else None
    sp_id = add_sub_program(
        category_id=cat_id,
        title=r.get("title", r.get("Title", "")).strip(),
        description=r.get("description", r.get("Description", "")).strip(),
        due_date=r.get("due_date", r.get("Due Date", "")) or None,
        in_charge_id=in_charge_id,
        recurring_type=r.get("recurring_type", "none").strip(),
        add_to_calendar=r.get("add_to_calendar", "0").strip() in ("1", "yes", "true"),
        type_flag=r.get("type_flag", "Program").strip(),
        notes=r.get("notes", r.get("Notes", "")).strip(),
    )
    for i in range(1, 11):
        t_title = r.get(f"task_{i}_title", r.get(f"Task {i} Title", "")).strip()
        if not t_title:
            continue
        add_task(
            sub_program_id=sp_id,
            title=t_title,
            due_date=r.get(f"task_{i}_due_date", r.get(f"Task {i} Due Date", "")) or None,
            assigned_to=int(r.get(f"task_{i}_assigned_to", "0") or 0) or None,
            priority=r.get(f"task_{i}_priority", "medium").strip(),
        )


# ─── CSV Export ──────────────────────────────────────────

@app.route("/export/members")
@login_required
def export_members_csv():
    conn = get_conn()
    rows = conn.execute("SELECT name, designation, phone, email FROM members ORDER BY name").fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["name", "designation", "phone", "email"])
    for r in rows:
        w.writerow([r["name"], r["designation"], r["phone"], r["email"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=members.csv"}


@app.route("/export/programs")
@login_required
def export_programs_csv():
    conn = get_conn()
    rows = conn.execute("SELECT name, description, sort_order FROM program_categories ORDER BY sort_order").fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["name", "description", "sort_order"])
    for r in rows:
        w.writerow([r["name"], r["description"], r["sort_order"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=program_categories.csv"}


@app.route("/export/sub_programs")
@login_required
def export_sub_programs_csv():
    conn = get_conn()
    subs = conn.execute("""
        SELECT sp.*, pc.name AS program_category
        FROM sub_programs sp
        LEFT JOIN program_categories pc ON sp.program_category_id = pc.id
        WHERE sp.parent_id IS NULL
        ORDER BY pc.name, sp.title
    """).fetchall()
    si = io.StringIO()
    w = csv.writer(si)
    cols = ["title", "program_category", "description", "due_date", "in_charge",
            "recurring_type", "add_to_calendar", "type_flag", "notes", "team_members",
            "task_1_title", "task_1_due_date", "task_1_assigned_to", "task_1_priority",
            "task_2_title", "task_2_due_date", "task_2_assigned_to", "task_2_priority",
            "task_3_title", "task_3_due_date", "task_3_assigned_to", "task_3_priority",
            "task_4_title", "task_4_due_date", "task_4_assigned_to", "task_4_priority",
            "task_5_title", "task_5_due_date", "task_5_assigned_to", "task_5_priority",
            "task_6_title", "task_6_due_date", "task_6_assigned_to", "task_6_priority",
            "task_7_title", "task_7_due_date", "task_7_assigned_to", "task_7_priority",
            "task_8_title", "task_8_due_date", "task_8_assigned_to", "task_8_priority",
            "task_9_title", "task_9_due_date", "task_9_assigned_to", "task_9_priority",
            "task_10_title", "task_10_due_date", "task_10_assigned_to", "task_10_priority"]
    w.writerow(cols)
    member_name_lookup = {m["id"]: m["name"] for m in get_members()}
    for sp in subs:
        sp = dict(sp)
        in_charge = member_name_lookup.get(sp["in_charge_id"], "")
        members = get_sub_program_members(sp["id"])
        team_ids = ",".join(str(m["member_id"]) for m in members)
        task_list, _ = get_tasks(sp["id"], per_page=500)
        row = [sp["title"], sp["program_category"] or "", sp["description"], sp["due_date"],
               in_charge, sp["recurring_type"], "1" if sp["add_to_calendar"] else "0",
               sp["type_flag"], sp["notes"], team_ids]
        for i in range(1, 11):
            t = task_list[i - 1] if i <= len(task_list) else None
            if t:
                assignee_name = member_name_lookup.get(t["assigned_to"], "")
                row.extend([t["title"], t["due_date"], assignee_name, t["priority"]])
            else:
                row.extend(["", "", "", ""])
        w.writerow(row)
    conn.close()
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=sub_programs.csv"}


@app.route("/export/tasks")
@login_required
def export_tasks_csv():
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.title, t.status, t.priority, t.due_date,
               m.name AS assigned_to, sp.title AS sub_program
        FROM tasks t
        LEFT JOIN members m ON t.assigned_to = m.id
        LEFT JOIN sub_programs sp ON t.sub_program_id = sp.id
        ORDER BY sp.title, t.id
    """).fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["sub_program", "title", "due_date", "assigned_to", "priority", "status"])
    for r in rows:
        w.writerow([r["sub_program"], r["title"], r["due_date"], r["assigned_to"], r["priority"], r["status"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=tasks.csv"}


@app.route("/export/events")
@login_required
def export_events_csv():
    conn = get_conn()
    rows = conn.execute("""
        SELECT e.title, e.type_flag, e.start_date, e.recurring_type,
               e.notes, sp.title AS sub_program
        FROM events e
        LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
        ORDER BY e.start_date
    """).fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["title", "start_date", "type_flag", "sub_program", "recurring_type", "notes"])
    for r in rows:
        w.writerow([r["title"], r["start_date"], r["type_flag"], r["sub_program"], r["recurring_type"], r["notes"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=events.csv"}


@app.route("/export/users")
@require_admin
def export_users_csv():
    conn = get_conn()
    rows = conn.execute("SELECT username, email, password_hash, role, display_name, is_approved FROM users ORDER BY id").fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["username", "email", "password_hash", "role", "display_name", "is_approved"])
    for r in rows:
        w.writerow([r["username"], r["email"], r["password_hash"], r["role"], r["display_name"], r["is_approved"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=users.csv"}


@app.route("/export/app_config")
@require_admin
def export_app_config_csv():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM app_config ORDER BY key").fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["key", "value"])
    for r in rows:
        w.writerow([r["key"], r["value"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=app_config.csv"}


@app.route("/export/sub_program_members")
@login_required
def export_sp_members_csv():
    conn = get_conn()
    rows = conn.execute("""
        SELECT sp.title AS sub_program_title, m.name AS member_name
        FROM sub_program_members spm
        JOIN sub_programs sp ON spm.sub_program_id = sp.id
        JOIN members m ON spm.member_id = m.id
        ORDER BY sp.title, m.name
    """).fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["sub_program_title", "member_name"])
    for r in rows:
        w.writerow([r["sub_program_title"], r["member_name"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=sub_program_members.csv"}


@app.route("/export/task_updates")
@login_required
def export_task_updates_csv():
    conn = get_conn()
    rows = conn.execute("""
        SELECT sp.title AS sub_program_title, t.title AS task_title,
               tu.note, tu.created_at
        FROM task_updates tu
        JOIN tasks t ON tu.task_id = t.id
        JOIN sub_programs sp ON t.sub_program_id = sp.id
        ORDER BY tu.id
    """).fetchall()
    conn.close()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["sub_program_title", "task_title", "note", "created_at"])
    for r in rows:
        w.writerow([r["sub_program_title"], r["task_title"], r["note"], r["created_at"]])
    out = si.getvalue()
    si.close()
    return out, 200, {"Content-Type": "text/csv", "Content-Disposition": "attachment; filename=task_updates.csv"}


@app.route("/export/backup")
@require_admin
def export_backup():
    conn = get_conn()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _backup_csv(zf, conn, "users", ["username", "email", "password_hash", "role", "display_name", "is_approved"],
                    "SELECT username, email, password_hash, role, display_name, is_approved FROM users ORDER BY id")
        _backup_csv(zf, conn, "app_config", ["key", "value"],
                    "SELECT key, value FROM app_config ORDER BY key")
        _backup_csv(zf, conn, "members", ["name", "designation", "phone", "email"],
                    "SELECT name, designation, phone, email FROM members ORDER BY name")
        _backup_csv(zf, conn, "program_categories", ["name", "description", "sort_order"],
                    "SELECT name, description, sort_order FROM program_categories ORDER BY sort_order")
        _backup_sub_programs_zip(zf, conn)
        _backup_csv(zf, conn, "sub_program_members", ["sub_program_title", "member_name"], """
            SELECT sp.title AS sub_program_title, m.name AS member_name
            FROM sub_program_members spm
            JOIN sub_programs sp ON spm.sub_program_id = sp.id
            JOIN members m ON spm.member_id = m.id
            ORDER BY sp.title, m.name
        """)
        _backup_csv(zf, conn, "tasks", ["sub_program", "title", "due_date", "assigned_to", "priority", "status"], """
            SELECT sp.title AS sub_program, t.title, t.due_date,
                   m.name AS assigned_to, t.priority, t.status
            FROM tasks t
            LEFT JOIN members m ON t.assigned_to = m.id
            LEFT JOIN sub_programs sp ON t.sub_program_id = sp.id
            ORDER BY sp.title, t.id
        """)
        _backup_csv(zf, conn, "task_updates", ["sub_program_title", "task_title", "note", "created_at"], """
            SELECT sp.title AS sub_program_title, t.title AS task_title,
                   tu.note, tu.created_at
            FROM task_updates tu
            JOIN tasks t ON tu.task_id = t.id
            JOIN sub_programs sp ON t.sub_program_id = sp.id
            ORDER BY tu.id
        """)
        _backup_csv(zf, conn, "events", ["title", "start_date", "type_flag", "sub_program", "recurring_type", "notes"], """
            SELECT e.title, e.start_date, e.type_flag,
                   sp.title AS sub_program, e.recurring_type, e.notes
            FROM events e
            LEFT JOIN sub_programs sp ON e.sub_program_id = sp.id
            ORDER BY e.start_date
        """)
    conn.close()
    buf.seek(0)
    return buf.read(), 200, {
        "Content-Type": "application/zip",
        "Content-Disposition": f"attachment; filename=chms-backup-{date.today().isoformat()}.zip",
    }


def _backup_csv(zf, conn, name, columns, sql):
    rows = conn.execute(sql).fetchall()
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(columns)
    for r in rows:
        w.writerow([r[c] for c in columns])
    zf.writestr(f"{name}.csv", si.getvalue().encode("utf-8"))
    si.close()


def _backup_sub_programs_zip(zf, conn):
    subs = conn.execute("""
        SELECT sp.*, pc.name AS program_category
        FROM sub_programs sp
        LEFT JOIN program_categories pc ON sp.program_category_id = pc.id
        WHERE sp.parent_id IS NULL
        ORDER BY pc.name, sp.title
    """).fetchall()
    member_names = {m["id"]: m["name"] for m in get_members()}
    si = io.StringIO()
    w = csv.writer(si)
    cols = ["title", "program_category", "description", "due_date", "in_charge",
            "recurring_type", "add_to_calendar", "type_flag", "notes", "team_members",
            "task_1_title", "task_1_due_date", "task_1_assigned_to", "task_1_priority",
            "task_2_title", "task_2_due_date", "task_2_assigned_to", "task_2_priority",
            "task_3_title", "task_3_due_date", "task_3_assigned_to", "task_3_priority",
            "task_4_title", "task_4_due_date", "task_4_assigned_to", "task_4_priority",
            "task_5_title", "task_5_due_date", "task_5_assigned_to", "task_5_priority",
            "task_6_title", "task_6_due_date", "task_6_assigned_to", "task_6_priority",
            "task_7_title", "task_7_due_date", "task_7_assigned_to", "task_7_priority",
            "task_8_title", "task_8_due_date", "task_8_assigned_to", "task_8_priority",
            "task_9_title", "task_9_due_date", "task_9_assigned_to", "task_9_priority",
            "task_10_title", "task_10_due_date", "task_10_assigned_to", "task_10_priority"]
    w.writerow(cols)
    for sp in subs:
        sp = dict(sp)
        in_charge = member_names.get(sp["in_charge_id"], "")
        sp_members = conn.execute(
            "SELECT member_id FROM sub_program_members WHERE sub_program_id=%s", (sp["id"],)
        ).fetchall()
        team_ids = ",".join(str(m["member_id"]) for m in sp_members)
        task_list, _ = get_tasks(sp["id"], per_page=500)
        row = [sp["title"], sp["program_category"] or "", sp["description"], sp["due_date"],
               in_charge, sp["recurring_type"], "1" if sp["add_to_calendar"] else "0",
               sp["type_flag"], sp["notes"], team_ids]
        for i in range(1, 11):
            t = task_list[i - 1] if i <= len(task_list) else None
            if t:
                assignee = member_names.get(t["assigned_to"], "")
                row.extend([t["title"], t["due_date"], assignee, t["priority"]])
            else:
                row.extend(["", "", "", ""])
        w.writerow(row)
    si.close()
    zf.writestr("sub_programs.csv", si.getvalue().encode("utf-8"))


# ─── Bootstrap ───────────────────────────────────────────

init_db()

if not os.environ.get("CHMS_TESTING"):
    admin_pw = os.environ.get("CHMS_ADMIN_PASSWORD", "qazcde@123")
    existing = get_user_by_email("admin@livingway.church")
    if not existing:
        add_user("admin", "admin@livingway.church", admin_pw, "admin", "Administrator", 1)
        print("Created admin user (admin@livingway.church)")


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"ChMS(prototype) starting on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
