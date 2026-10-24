from __future__ import annotations

import os
import secrets
import sqlite3
import json
import csv
import io
from werkzeug.utils import secure_filename
from flask import send_file
from functools import wraps
from pathlib import Path
from datetime import timedelta

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("MONSTROART_DATABASE", BASE_DIR / "instance" / "monstroart.sqlite3"))
UPLOAD_DIR = Path(os.environ.get("MONSTROART_UPLOAD_DIR", BASE_DIR / "instance" / "uploads"))
ALLOWED_UPLOADS = {"pdf", "png", "jpg", "jpeg", "webp", "gif", "txt", "doc", "docx", "ppt", "pptx", "zip", "mp4", "webm", "mp3", "wav", "svg"}
OWNER_EMAIL = os.environ.get("MONSTROART_OWNER_EMAIL", "talipov.aday@gmail.com").strip().lower()

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("MONSTROART_SECRET_KEY", "dev-only-change-this-key-before-deployment"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("MONSTROART_HTTPS", "0") == "1",
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        display_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    # Safe, additive migration for existing local databases.
    columns = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "role" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
    db.execute("""CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        activity_type TEXT NOT NULL CHECK(activity_type IN ('contest','olympiad')),
        subject TEXT NOT NULL DEFAULT 'Общее',
        deadline TEXT NOT NULL DEFAULT '',
        created_by INTEGER NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_open INTEGER NOT NULL DEFAULT 1
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS activity_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(activity_id, user_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        message TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'info',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        read_at TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS one_time_grants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        granted_by INTEGER NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        used_at TEXT
    )""")
    # Additive learning, submissions, quiz, and account-preference tables.
    entry_columns = {row[1] for row in db.execute("PRAGMA table_info(activity_entries)").fetchall()}
    if "score" not in entry_columns:
        db.execute("ALTER TABLE activity_entries ADD COLUMN score INTEGER NOT NULL DEFAULT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS activity_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
        prompt TEXT NOT NULL,
        question_type TEXT NOT NULL DEFAULT 'single',
        options_json TEXT NOT NULL DEFAULT '[]',
        correct_answer TEXT NOT NULL DEFAULT '',
        points INTEGER NOT NULL DEFAULT 1,
        position INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS activity_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        stored_name TEXT NOT NULL,
        original_name TEXT NOT NULL,
        comment TEXT NOT NULL DEFAULT '',
        score INTEGER,
        feedback TEXT NOT NULL DEFAULT '',
        submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(activity_id, user_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        answers_json TEXT NOT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        max_score INTEGER NOT NULL DEFAULT 0,
        submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(activity_id, user_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        subject TEXT NOT NULL DEFAULT 'Общее',
        created_by INTEGER NOT NULL REFERENCES users(id),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        is_published INTEGER NOT NULL DEFAULT 1
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS course_lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        position INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS course_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lesson_id INTEGER NOT NULL REFERENCES course_lessons(id) ON DELETE CASCADE,
        stored_name TEXT NOT NULL,
        original_name TEXT NOT NULL,
        mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS course_enrollments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        enrolled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(course_id, user_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS course_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        lesson_id INTEGER NOT NULL REFERENCES course_lessons(id) ON DELETE CASCADE,
        completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, lesson_id)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        theme TEXT NOT NULL DEFAULT 'light',
        public_profile INTEGER NOT NULL DEFAULT 1,
        email_updates INTEGER NOT NULL DEFAULT 1
    )""")
    # The configured owner email is elevated on startup; no password is stored in source.
    db.execute("UPDATE users SET role='owner' WHERE lower(email)=lower(?)", (OWNER_EMAIL,))
    db.commit()


@app.before_request
def prepare_request() -> None:
    init_db()
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    g.user = None
    user_id = session.get("user_id")
    g.theme = "light"
    if user_id:
        g.user = get_db().execute(
            "SELECT id, display_name, email, created_at, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:
            session.clear()
        else:
            pref = get_db().execute("SELECT theme FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
            if pref and pref["theme"] in ("light", "dark"):
                g.theme = pref["theme"]


def csrf_valid() -> bool:
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(sent and expected and secrets.compare_digest(sent, expected))


def require_csrf() -> None:
    if not csrf_valid():
        abort(400, description="Форма устарела. Обнови страницу и попробуй снова.")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Сначала войди в аккаунт.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def safe_next_url(value: str | None) -> str | None:
    if value and value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return None


def unread_notifications(user_id: int):
    return get_db().execute(
        "SELECT * FROM notifications WHERE user_id=? AND read_at IS NULL ORDER BY id DESC LIMIT 8", (user_id,)
    ).fetchall()


@app.get("/")
def index():
    db = get_db()
    activities = db.execute("SELECT a.*, u.display_name AS creator, (SELECT COUNT(*) FROM activity_entries e WHERE e.activity_id=a.id) AS participants FROM activities a JOIN users u ON u.id=a.created_by WHERE a.is_open=1 ORDER BY a.created_at DESC LIMIT 6").fetchall()
    return render_template("index.html", activities=activities)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("account"))
    next_url = safe_next_url(request.args.get("next") or request.form.get("next"))
    if request.method == "POST":
        require_csrf()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = request.form.get("remember") == "on"
            session["csrf_token"] = secrets.token_urlsafe(32)
            flash(f"С возвращением, {user['display_name']}!", "success")
            return redirect(next_url or url_for("account"))
        flash("Не получилось войти. Проверь email и пароль.", "error")
    return render_template("auth.html", mode="login", next_url=next_url or "")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("account"))
    if request.method == "POST":
        require_csrf()
        display_name = " ".join(request.form.get("name", "").split())
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        accepted = request.form.get("consent") == "on"
        errors = []
        if len(display_name) < 2 or len(display_name) > 70:
            errors.append("Укажи имя длиной от 2 до 70 символов.")
        if len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@"):
            errors.append("Укажи корректный email.")
        if len(password) < 8:
            errors.append("Пароль должен содержать не менее 8 символов.")
        if password != confirm:
            errors.append("Пароли не совпадают.")
        if not accepted:
            errors.append("Нужно подтвердить согласие на обработку данных.")
        if get_db().execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            errors.append("Аккаунт с таким email уже существует.")
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("auth.html", mode="register", form_name=display_name, form_email=email)
        role = "owner" if email.lower() == OWNER_EMAIL else "student"
        cursor = get_db().execute(
            "INSERT INTO users (display_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (display_name, email, generate_password_hash(password), role),
        )
        get_db().commit()
        session.clear()
        session["user_id"] = cursor.lastrowid
        session["csrf_token"] = secrets.token_urlsafe(32)
        if role == "owner":
            flash("Аккаунт владельца MonstroArt создан.", "success")
        else:
            flash("Аккаунт создан. Добро пожаловать в MonstroArt!", "success")
        return redirect(url_for("account"))
    return render_template("auth.html", mode="register", form_name="", form_email="")


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    db = get_db()
    if request.method == "POST":
        require_csrf()
        display_name = " ".join(request.form.get("display_name", "").split())
        if len(display_name) < 2 or len(display_name) > 70:
            flash("Имя должно содержать от 2 до 70 символов.", "error")
        else:
            db.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, g.user["id"]))
            db.commit()
            flash("Профиль сохранён.", "success")
            return redirect(url_for("account"))
    user = db.execute("SELECT id, display_name, email, created_at, role FROM users WHERE id = ?", (g.user["id"],)).fetchone()
    joined = db.execute("SELECT a.*, e.joined_at FROM activity_entries e JOIN activities a ON a.id=e.activity_id WHERE e.user_id=? ORDER BY e.joined_at DESC", (user["id"],)).fetchall()
    unread = unread_notifications(user["id"])
    grant_count = db.execute("SELECT COUNT(*) FROM one_time_grants WHERE user_id=? AND used_at IS NULL", (user["id"],)).fetchone()[0]
    stats = {
        "activities": len(joined),
        "olympiads": sum(1 for item in joined if item["activity_type"] == "olympiad"),
        "unread": len(unread),
    }
    created = db.execute("SELECT * FROM activities WHERE created_by=? ORDER BY created_at DESC LIMIT 5", (user["id"],)).fetchall()
    settings = db.execute("SELECT * FROM user_settings WHERE user_id=?", (user["id"],)).fetchone()
    if settings is None:
        db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user["id"],)); db.commit()
        settings = db.execute("SELECT * FROM user_settings WHERE user_id=?", (user["id"],)).fetchone()
    score = db.execute("SELECT COALESCE(SUM(score),0) FROM activity_entries WHERE user_id=?", (user["id"],)).fetchone()[0]
    return render_template("account.html", user=user, joined=joined, notifications=unread, grant_count=grant_count, stats=stats, created=created, settings=settings, score=score)


@app.get("/activities")
def activities():
    db = get_db()
    items = db.execute("SELECT a.*, u.display_name AS creator, (SELECT COUNT(*) FROM activity_entries e WHERE e.activity_id=a.id) AS participants FROM activities a JOIN users u ON u.id=a.created_by WHERE a.is_open=1 ORDER BY a.created_at DESC").fetchall()
    joined_ids = set()
    if g.user:
        joined_ids = {row[0] for row in db.execute("SELECT activity_id FROM activity_entries WHERE user_id=?", (g.user["id"],)).fetchall()}
    return render_template("activities.html", activities=items, joined_ids=joined_ids)


@app.post("/activities/<int:activity_id>/join")
@login_required
def join_activity(activity_id):
    require_csrf()
    db = get_db()
    item = db.execute("SELECT * FROM activities WHERE id=? AND is_open=1", (activity_id,)).fetchone()
    if item is None:
        abort(404)
    try:
        db.execute("INSERT INTO activity_entries (activity_id, user_id) VALUES (?, ?)", (activity_id, g.user["id"]))
        db.commit()
        flash("Ты записан(а)! Активность появилась в твоём профиле.", "success")
    except sqlite3.IntegrityError:
        flash("Ты уже участвуешь в этой активности.", "info")
    return redirect(url_for("activities"))


@app.post("/activities/create")
@login_required
def create_activity():
    require_csrf()
    db = get_db()
    role = g.user["role"]
    activity_type = request.form.get("activity_type", "contest")
    has_grant = db.execute("SELECT id FROM one_time_grants WHERE user_id=? AND used_at IS NULL ORDER BY id LIMIT 1", (g.user["id"],)).fetchone() if role == "student" else None
    if role not in ("owner", "teacher") and not (role == "student" and has_grant and activity_type == "contest"):
        abort(403)
    title = " ".join(request.form.get("title", "").split())[:120]
    description = request.form.get("description", "").strip()[:2000]
    subject = " ".join(request.form.get("subject", "Общее").split())[:80] or "Общее"
    deadline = request.form.get("deadline", "").strip()[:10]
    if activity_type not in ("contest", "olympiad") or (role == "student" and activity_type != "contest"):
        abort(403)
    if len(title) < 3 or len(description) < 8:
        flash("Добавь название (минимум 3 символа) и описание (минимум 8 символов).", "error")
        return redirect(url_for("account"))
    cur = db.execute("INSERT INTO activities (title, description, activity_type, subject, deadline, created_by) VALUES (?, ?, ?, ?, ?, ?)", (title, description, activity_type, subject, deadline, g.user["id"]))
    activity_id = cur.lastrowid
    if activity_type == "olympiad":
        prompts = request.form.getlist("question_prompt[]")
        types = request.form.getlist("question_type[]")
        options_list = request.form.getlist("question_options[]")
        correct_list = request.form.getlist("question_correct[]")
        points_list = request.form.getlist("question_points[]")
        for idx, prompt in enumerate(prompts[:30]):
            prompt = prompt.strip()[:500]
            if not prompt:
                continue
            qtype = types[idx] if idx < len(types) and types[idx] in ("single", "text") else "single"
            opts = [x.strip()[:120] for x in (options_list[idx].splitlines() if idx < len(options_list) else []) if x.strip()][:8]
            correct = (correct_list[idx].strip()[:200] if idx < len(correct_list) else "")
            points = max(1, min(100, int(points_list[idx] or 1))) if idx < len(points_list) and points_list[idx].isdigit() else 1
            if qtype == "single" and len(opts) < 2:
                continue
            db.execute("INSERT INTO activity_questions (activity_id,prompt,question_type,options_json,correct_answer,points,position) VALUES (?,?,?,?,?,?,?)", (activity_id,prompt,qtype,json.dumps(opts,ensure_ascii=False),correct,points,idx))
    if has_grant and role == "student":
        db.execute("UPDATE one_time_grants SET used_at=CURRENT_TIMESTAMP WHERE id=?", (has_grant["id"],))
        db.execute("INSERT INTO notifications (user_id, message, kind) VALUES (?, ?, 'success')", (g.user["id"], f"Разовый доступ использован: конкурс «{title}» создан."))
    db.commit()
    flash("Конкурс создан!" if activity_type == "contest" else "Олимпиада создана!", "success")
    return redirect(url_for("activities"))


@app.get("/leaderboard")
def leaderboard():
    rows = get_db().execute("""SELECT u.id,u.display_name,u.role,COALESCE(SUM(e.score),0) AS points,
        COUNT(DISTINCT e.activity_id) AS participations,
        (SELECT COUNT(*) FROM quiz_attempts q WHERE q.user_id=u.id) AS quizzes
        FROM users u LEFT JOIN activity_entries e ON e.user_id=u.id
        WHERE u.role!='owner' AND COALESCE((SELECT public_profile FROM user_settings us WHERE us.user_id=u.id),1)=1 GROUP BY u.id ORDER BY points DESC, participations DESC, u.display_name COLLATE NOCASE LIMIT 100""").fetchall()
    return render_template("leaderboard.html", rows=rows)


@app.get("/settings")
@login_required
def settings():
    db=get_db(); row=db.execute("SELECT * FROM user_settings WHERE user_id=?",(g.user["id"],)).fetchone()
    if row is None:
        db.execute("INSERT OR IGNORE INTO user_settings(user_id) VALUES (?)",(g.user["id"],)); db.commit()
        row=db.execute("SELECT * FROM user_settings WHERE user_id=?",(g.user["id"],)).fetchone()
    return render_template("settings.html", settings=row)


@app.post("/settings")
@login_required
def save_settings():
    require_csrf(); theme=request.form.get("theme","light")
    if theme not in ("light","dark"): theme="light"
    public_profile=1 if request.form.get("public_profile")=="on" else 0
    email_updates=1 if request.form.get("email_updates")=="on" else 0
    db=get_db(); db.execute("INSERT INTO user_settings(user_id,theme,public_profile,email_updates) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme,public_profile=excluded.public_profile,email_updates=excluded.email_updates",(g.user["id"],theme,public_profile,email_updates)); db.commit()
    flash("Настройки сохранены.","success"); return redirect(url_for("settings"))


@app.get("/courses")
def courses():
    db=get_db()
    items=db.execute("""SELECT c.*,u.display_name AS creator,(SELECT COUNT(*) FROM course_lessons l WHERE l.course_id=c.id) AS lesson_count,
      (SELECT COUNT(*) FROM course_enrollments e WHERE e.course_id=c.id) AS students FROM courses c JOIN users u ON u.id=c.created_by WHERE c.is_published=1 ORDER BY c.created_at DESC""").fetchall()
    joined=set()
    if g.user: joined={r[0] for r in db.execute("SELECT course_id FROM course_enrollments WHERE user_id=?",(g.user["id"],)).fetchall()}
    return render_template("courses.html", courses=items, joined=joined)


@app.get("/courses/create")
@roles_required("owner","teacher")
def course_create_page():
    return render_template("course_create.html")


@app.post("/courses/create")
@roles_required("owner","teacher")
def create_course():
    require_csrf(); db=get_db()
    title=" ".join(request.form.get("title","").split())[:120]; description=request.form.get("description","").strip()[:2000]; subject=" ".join(request.form.get("subject","Общее").split())[:80] or "Общее"
    if len(title)<3 or len(description)<8:
        flash("Укажи название и описание курса.","error"); return redirect(url_for("course_create_page"))
    cur=db.execute("INSERT INTO courses(title,description,subject,created_by) VALUES(?,?,?,?)",(title,description,subject,g.user["id"]))
    lesson_titles=request.form.getlist("lesson_title[]"); lesson_contents=request.form.getlist("lesson_content[]")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for i, lesson_title in enumerate(lesson_titles[:40]):
        content=lesson_contents[i].strip()[:12000] if i<len(lesson_contents) else ""
        if lesson_title.strip() and content:
            lesson_cur = db.execute("INSERT INTO course_lessons(course_id,title,content,position) VALUES(?,?,?,?)",(cur.lastrowid,lesson_title.strip()[:160],content,i))
            lesson_id = lesson_cur.lastrowid
            for uploaded in request.files.getlist(f"lesson_files_{i}[]")[:10]:
                if not uploaded or not uploaded.filename:
                    continue
                original = secure_filename(uploaded.filename)[:180]
                ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
                if ext not in ALLOWED_UPLOADS:
                    continue
                stored = secrets.token_hex(16) + "." + ext
                uploaded.save(UPLOAD_DIR / stored)
                db.execute("INSERT INTO course_materials(lesson_id,stored_name,original_name,mime_type) VALUES(?,?,?,?)", (lesson_id, stored, original, uploaded.mimetype or "application/octet-stream"))
    db.commit(); flash("Курс опубликован с уроками и материалами!","success"); return redirect(url_for("course_detail",course_id=cur.lastrowid))


@app.post("/courses/<int:course_id>/enroll")
@login_required
def enroll_course(course_id):
    require_csrf(); db=get_db()
    if not db.execute("SELECT 1 FROM courses WHERE id=? AND is_published=1",(course_id,)).fetchone(): abort(404)
    db.execute("INSERT OR IGNORE INTO course_enrollments(course_id,user_id) VALUES(?,?)",(course_id,g.user["id"])); db.commit(); flash("Курс добавлен в твоё обучение.","success"); return redirect(url_for("course_detail",course_id=course_id))


@app.get("/courses/<int:course_id>")
def course_detail(course_id):
    db=get_db(); course=db.execute("SELECT c.*,u.display_name AS creator FROM courses c JOIN users u ON u.id=c.created_by WHERE c.id=? AND c.is_published=1",(course_id,)).fetchone()
    if not course: abort(404)
    lessons=db.execute("SELECT * FROM course_lessons WHERE course_id=? ORDER BY position,id",(course_id,)).fetchall(); completed=set()
    materials_by_lesson = {}
    for lesson_row in lessons:
        materials_by_lesson[lesson_row["id"]] = db.execute("SELECT * FROM course_materials WHERE lesson_id=? ORDER BY id", (lesson_row["id"],)).fetchall()
    enrolled=False
    can_preview=False
    if g.user:
        enrolled=bool(db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND user_id=?",(course_id,g.user["id"])).fetchone())
        can_preview=(g.user["role"]=="owner" or course["created_by"]==g.user["id"])
        completed={r[0] for r in db.execute("SELECT cp.lesson_id FROM course_progress cp JOIN course_lessons l ON l.id=cp.lesson_id WHERE l.course_id=? AND cp.user_id=?",(course_id,g.user["id"])).fetchall()}
    return render_template("course_detail.html",course=course,lessons=lessons,completed=completed,enrolled=enrolled,can_preview=can_preview,materials_by_lesson=materials_by_lesson)


@app.get("/courses/materials/<int:material_id>")
def course_material(material_id):
    db = get_db()
    row = db.execute("SELECT m.*,l.course_id,c.created_by FROM course_materials m JOIN course_lessons l ON l.id=m.lesson_id JOIN courses c ON c.id=l.course_id WHERE m.id=? AND c.is_published=1", (material_id,)).fetchone()
    if not row:
        abort(404)
    if not g.user:
        abort(403)
    allowed = g.user["role"] == "owner" or row["created_by"] == g.user["id"] or db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND user_id=?", (row["course_id"], g.user["id"])).fetchone()
    if not allowed:
        abort(403)
    path = UPLOAD_DIR / row["stored_name"]
    if not path.is_file():
        abort(404)
    inline = Path(row["original_name"]).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm", ".mp3", ".wav"}
    return send_file(path, mimetype=row["mime_type"], as_attachment=not inline, download_name=row["original_name"])


@app.post("/courses/lessons/<int:lesson_id>/complete")
@login_required
def complete_lesson(lesson_id):
    require_csrf(); db=get_db(); lesson=db.execute("SELECT l.*,c.id AS course_id FROM course_lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=?",(lesson_id,)).fetchone()
    if not lesson: abort(404)
    if not db.execute("SELECT 1 FROM course_enrollments WHERE course_id=? AND user_id=?",(lesson["course_id"],g.user["id"])).fetchone(): abort(403)
    db.execute("INSERT OR IGNORE INTO course_progress(user_id,lesson_id) VALUES(?,?)",(g.user["id"],lesson_id)); db.commit(); flash("Урок отмечен как пройденный.","success"); return redirect(url_for("course_detail",course_id=lesson["course_id"]))


@app.get("/activities/<int:activity_id>")
def activity_detail(activity_id):
    db=get_db(); item=db.execute("SELECT a.*,u.display_name AS creator FROM activities a JOIN users u ON u.id=a.created_by WHERE a.id=?",(activity_id,)).fetchone()
    if not item: abort(404)
    questions=db.execute("SELECT id,prompt,question_type,options_json,points,position FROM activity_questions WHERE activity_id=? ORDER BY position,id",(activity_id,)).fetchall()
    questions=[dict(q,options=json.loads(q["options_json"])) for q in questions]
    entry=db.execute("SELECT * FROM activity_entries WHERE activity_id=? AND user_id=?",(activity_id,g.user["id"])).fetchone() if g.user else None
    attempt=db.execute("SELECT * FROM quiz_attempts WHERE activity_id=? AND user_id=?",(activity_id,g.user["id"])).fetchone() if g.user else None
    submission=db.execute("SELECT * FROM activity_submissions WHERE activity_id=? AND user_id=?",(activity_id,g.user["id"])).fetchone() if g.user else None
    submissions=[]
    if g.user and g.user["role"] in ("owner","teacher") and (g.user["role"]=="owner" or item["created_by"]==g.user["id"]):
        submissions=db.execute("SELECT s.*,u.display_name,u.email FROM activity_submissions s JOIN users u ON u.id=s.user_id WHERE s.activity_id=? ORDER BY s.submitted_at DESC",(activity_id,)).fetchall()
    return render_template("activity_detail.html",item=item,questions=questions,entry=entry,attempt=attempt,submission=submission,submissions=submissions)


@app.post("/activities/<int:activity_id>/submit")
@login_required
def submit_activity(activity_id):
    require_csrf(); db=get_db(); item=db.execute("SELECT * FROM activities WHERE id=? AND is_open=1",(activity_id,)).fetchone()
    if not item: abort(404)
    if not db.execute("SELECT 1 FROM activity_entries WHERE activity_id=? AND user_id=?",(activity_id,g.user["id"])).fetchone(): abort(403)
    if item["activity_type"]=="contest":
        file=request.files.get("work_file")
        comment=request.form.get("comment","").strip()[:1500]
        if not file or not file.filename:
            flash("Прикрепи файл своей работы.","error"); return redirect(url_for("activity_detail",activity_id=activity_id))
        original=secure_filename(file.filename)
        ext=original.rsplit(".",1)[-1].lower() if "." in original else ""
        if ext not in ALLOWED_UPLOADS: flash("Этот тип файла не поддерживается.","error"); return redirect(url_for("activity_detail",activity_id=activity_id))
        UPLOAD_DIR.mkdir(parents=True,exist_ok=True); stored=secrets.token_hex(16)+"."+ext; file.save(UPLOAD_DIR/stored)
        old=db.execute("SELECT stored_name FROM activity_submissions WHERE activity_id=? AND user_id=?",(activity_id,g.user["id"])).fetchone()
        if old:
            try: (UPLOAD_DIR/old["stored_name"]).unlink(missing_ok=True)
            except OSError: pass
        db.execute("INSERT INTO activity_submissions(activity_id,user_id,stored_name,original_name,comment) VALUES(?,?,?,?,?) ON CONFLICT(activity_id,user_id) DO UPDATE SET stored_name=excluded.stored_name,original_name=excluded.original_name,comment=excluded.comment,submitted_at=CURRENT_TIMESTAMP",(activity_id,g.user["id"],stored,original,comment)); db.commit()
        flash("Работа отправлена на оценку!","success")
    else:
        questions=db.execute("SELECT * FROM activity_questions WHERE activity_id=? ORDER BY position,id",(activity_id,)).fetchall(); answers={}; score=0; max_score=0
        for q in questions:
            answer=request.form.get(f"q_{q['id']}","").strip()[:500]; answers[str(q["id"])]=answer; max_score+=q["points"]
            if q["correct_answer"].strip().casefold()==answer.casefold() and answer: score+=q["points"]
        if not questions:
            flash("В этой олимпиаде пока нет заданий.","info"); return redirect(url_for("activity_detail",activity_id=activity_id))
        db.execute("INSERT INTO quiz_attempts(activity_id,user_id,answers_json,score,max_score) VALUES(?,?,?,?,?) ON CONFLICT(activity_id,user_id) DO UPDATE SET answers_json=excluded.answers_json,score=excluded.score,max_score=excluded.max_score,submitted_at=CURRENT_TIMESTAMP",(activity_id,g.user["id"],json.dumps(answers,ensure_ascii=False),score,max_score))
        db.execute("UPDATE activity_entries SET score=? WHERE activity_id=? AND user_id=?",(score,activity_id,g.user["id"]))
        db.commit(); flash(f"Ответы отправлены! Результат: {score} из {max_score} баллов.","success")
    return redirect(url_for("activity_detail",activity_id=activity_id))


@app.post("/uploads/submissions/<int:submission_id>/grade")
@roles_required("owner","teacher")
def grade_submission(submission_id):
    require_csrf(); db=get_db()
    row=db.execute("SELECT s.*,a.created_by FROM activity_submissions s JOIN activities a ON a.id=s.activity_id WHERE s.id=?",(submission_id,)).fetchone()
    if not row: abort(404)
    if g.user["role"]!="owner" and row["created_by"]!=g.user["id"]: abort(403)
    score=request.form.get("score",type=int)
    if score is None or score<0 or score>1000:
        flash("Оценка должна быть от 0 до 1000.","error"); return redirect(url_for("activity_detail",activity_id=row["activity_id"]))
    feedback=request.form.get("feedback","").strip()[:1000]
    db.execute("UPDATE activity_submissions SET score=?,feedback=? WHERE id=?",(score,feedback,submission_id))
    db.execute("UPDATE activity_entries SET score=? WHERE activity_id=? AND user_id=?",(score,row["activity_id"],row["user_id"]))
    db.execute("INSERT INTO notifications(user_id,message,kind) VALUES(?,?, 'success')",(row["user_id"],f"Работа по конкурсу проверена. Баллы: {score}."))
    db.commit(); flash("Оценка сохранена, участник получил уведомление.","success"); return redirect(url_for("activity_detail",activity_id=row["activity_id"]))


@app.get("/uploads/submissions/<int:submission_id>")
@roles_required("owner","teacher")
def download_submission(submission_id):
    row=get_db().execute("SELECT s.*,a.created_by FROM activity_submissions s JOIN activities a ON a.id=s.activity_id WHERE s.id=?",(submission_id,)).fetchone()
    if not row: abort(404)
    if g.user["role"]!="owner" and row["created_by"]!=g.user["id"]: abort(403)
    path=UPLOAD_DIR/row["stored_name"]
    if not path.is_file(): abort(404)
    return send_file(path,as_attachment=True,download_name=row["original_name"])


@app.post("/notifications/<int:notification_id>/read")
@login_required
def read_notification(notification_id):
    require_csrf()
    get_db().execute("UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (notification_id, g.user["id"]))
    get_db().commit()
    return redirect(url_for("account"))


@app.route("/admin", methods=["GET", "POST"])
@roles_required("owner")
def admin():
    db = get_db()
    if request.method == "POST":
        require_csrf()
        action = request.form.get("action", "")
        target_id = request.form.get("user_id", type=int)
        target = db.execute("SELECT id, display_name, email, role FROM users WHERE id=?", (target_id,)).fetchone() if target_id else None
        if action == "role" and target:
            new_role = request.form.get("role", "student")
            if target["role"] == "owner" or new_role not in ("student", "teacher"):
                flash("Роль владельца нельзя изменить из панели.", "error")
            else:
                db.execute("UPDATE users SET role=? WHERE id=?", (new_role, target_id))
                db.commit()
                flash(f"Роль пользователя {target['display_name']} обновлена.", "success")
        elif action == "grant" and target:
            if target["role"] != "student":
                flash("Разовый доступ можно выдавать только ученикам.", "error")
            else:
                db.execute("INSERT INTO one_time_grants (user_id, granted_by) VALUES (?, ?)", (target_id, g.user["id"]))
                db.execute("INSERT INTO notifications (user_id, message, kind) VALUES (?, ?, 'success')", (target_id, f"Тебе выдан разовый доступ на создание конкурса. Используй его в личном кабинете — это твой шанс проявить себя!"))
                db.commit()
                flash(f"Ученику {target['display_name']} выдан разовый доступ и отправлено уведомление.", "success")
        return redirect(url_for("admin"))
    users = db.execute("SELECT u.id, u.display_name, u.email, u.role, u.created_at, (SELECT COUNT(*) FROM activities a WHERE a.created_by=u.id) AS created_count, (SELECT COUNT(*) FROM one_time_grants g WHERE g.user_id=u.id AND g.used_at IS NULL) AS grants_left FROM users u ORDER BY CASE u.role WHEN 'owner' THEN 0 WHEN 'teacher' THEN 1 ELSE 2 END, u.created_at DESC").fetchall()
    counts = {
        "users": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "teachers": db.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0],
        "activities": db.execute("SELECT COUNT(*) FROM activities").fetchone()[0],
        "pending_grants": db.execute("SELECT COUNT(*) FROM one_time_grants WHERE used_at IS NULL").fetchone()[0],
        "courses": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "submissions": db.execute("SELECT COUNT(*) FROM activity_submissions").fetchone()[0],
    }
    return render_template("admin.html", users=users, counts=counts)


@app.get("/admin/database/export")
@roles_required("owner")
def export_database():
    db=get_db(); tables=["activities","activity_entries","activity_questions","courses","course_lessons","course_enrollments","course_progress","notifications","one_time_grants","quiz_attempts","activity_submissions","user_settings"]
    payload={"format":"monstroart-json-v1","exported_at":__import__("datetime").datetime.utcnow().isoformat()+"Z","tables":{}}
    for table in tables:
        payload["tables"][table]=[dict(row) for row in db.execute(f"SELECT * FROM {table}").fetchall()]
    # Account password hashes are intentionally excluded from exports.
    payload["tables"]["users"]=[{k:v for k,v in dict(row).items() if k!="password_hash"} for row in db.execute("SELECT * FROM users").fetchall()]
    data=json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8")
    return send_file(io.BytesIO(data),mimetype="application/json",as_attachment=True,download_name="monstroart-backup.json")


@app.post("/admin/database/import")
@roles_required("owner")
def import_database():
    require_csrf(); uploaded=request.files.get("backup")
    if not uploaded or not uploaded.filename or not uploaded.filename.lower().endswith(".json"):
        flash("Выбери JSON-файл резервной копии MonstroArt.","error"); return redirect(url_for("admin"))
    raw=uploaded.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: flash("Файл больше 5 МБ.","error"); return redirect(url_for("admin"))
    try: payload=json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError,json.JSONDecodeError): flash("Не удалось прочитать JSON.","error"); return redirect(url_for("admin"))
    if payload.get("format")!="monstroart-json-v1" or not isinstance(payload.get("tables"),dict):
        flash("Это не резервная копия MonstroArt нужного формата.","error"); return redirect(url_for("admin"))
    # Safe additive import: import only courses and activities, never accounts or permissions.
    db=get_db(); imported=0
    for row in payload["tables"].get("activities",[])[:500]:
        try:
            title=str(row.get("title", "")).strip()[:120]; desc=str(row.get("description", "")).strip()[:2000]
            if len(title)<3 or len(desc)<8: continue
            creator=db.execute("SELECT id FROM users WHERE id=?",(row.get("created_by"),)).fetchone()
            if not creator: creator=db.execute("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
            if not creator: continue
            exists=db.execute("SELECT 1 FROM activities WHERE title=? AND description=?",(title,desc)).fetchone()
            if exists: continue
            db.execute("INSERT INTO activities(title,description,activity_type,subject,deadline,created_by,is_open) VALUES(?,?,?,?,?,?,?)",(title,desc,row.get("activity_type") if row.get("activity_type") in ("contest","olympiad") else "contest",str(row.get("subject","Общее"))[:80],str(row.get("deadline",""))[:10],creator["id"],1)); imported+=1
        except (sqlite3.Error,TypeError,ValueError): continue
    imported_courses=0
    for row in payload["tables"].get("courses",[])[:200]:
        try:
            title=str(row.get("title","")).strip()[:120]; desc=str(row.get("description","")).strip()[:2000]
            if len(title)<3 or len(desc)<8 or db.execute("SELECT 1 FROM courses WHERE title=?",(title,)).fetchone(): continue
            creator=db.execute("SELECT id FROM users WHERE id=?",(row.get("created_by"),)).fetchone() or db.execute("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1").fetchone()
            if not creator: continue
            cur=db.execute("INSERT INTO courses(title,description,subject,created_by,is_published) VALUES(?,?,?,?,1)",(title,desc,str(row.get("subject","Общее"))[:80],creator["id"]))
            lesson_rows=[l for l in payload["tables"].get("course_lessons",[]) if l.get("course_id")==row.get("id")][:40]
            for i, lesson in enumerate(lesson_rows):
                lesson_title=str(lesson.get("title","")).strip()[:160]; content=str(lesson.get("content","")).strip()[:12000]
                if lesson_title and content: db.execute("INSERT INTO course_lessons(course_id,title,content,position) VALUES(?,?,?,?)",(cur.lastrowid,lesson_title,content,i))
            imported_courses+=1
        except (sqlite3.Error,TypeError,ValueError): continue
    db.commit(); flash(f"Импорт завершён: активностей — {imported}, курсов — {imported_courses}. Учётные записи и роли не импортировались.","success"); return redirect(url_for("admin"))


@app.post("/teacher/grant")
@roles_required("owner", "teacher")
def teacher_grant():
    require_csrf()
    email = request.form.get("email", "").strip().lower()
    db = get_db()
    target = db.execute("SELECT id, display_name, role FROM users WHERE lower(email)=?", (email,)).fetchone()
    if not target:
        flash("Пользователь с таким email не найден. Пусть сначала создаст аккаунт.", "error")
    elif target["role"] != "student":
        flash("Разовый доступ можно выдавать только ученикам.", "error")
    else:
        db.execute("INSERT INTO one_time_grants (user_id, granted_by) VALUES (?, ?)", (target["id"], g.user["id"]))
        db.execute("INSERT INTO notifications (user_id, message, kind) VALUES (?, ?, 'success')", (target["id"], "Тебе выдан разовый доступ на создание конкурса. Используй его в личном кабинете — это твой шанс проявить себя!"))
        db.commit()
        flash(f"Разовый доступ выдан ученику {target['display_name']}. Уведомление отправлено в профиль.", "success")
    return redirect(url_for("account"))


@app.post("/logout")
@login_required
def logout():
    require_csrf()
    session.clear()
    flash("Ты вышел из аккаунта.", "info")
    return redirect(url_for("index"))


@app.post("/oauth/google")
def google_oauth_placeholder():
    require_csrf()
    flash("Вход через Google пока не подключён. Используй email и пароль.", "info")
    return redirect(request.referrer if safe_next_url(request.referrer) else url_for("login"))


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/health")
def health():
    return {"status": "ok", "app": "MonstroArt"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
