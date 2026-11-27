import os
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, jsonify, render_template, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, inspect, text
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
database_url = os.environ.get("DATABASE_URL", "sqlite:///neuroquest.db").strip()
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "local-development-only-change-this"),
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER_EXTERNAL_HOSTNAME")),
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    MAX_CONTENT_LENGTH=32 * 1024,
)
db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(24), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    total_xp = db.Column(db.Integer, default=0, nullable=False)
    best_round = db.Column(db.Integer, default=0, nullable=False)
    rounds_completed = db.Column(db.Integer, default=0, nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    current_streak = db.Column(db.Integer, default=0, nullable=False)
    longest_streak = db.Column(db.Integer, default=0, nullable=False)
    last_play_date = db.Column(db.Date, nullable=True)


class RoundResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    game = db.Column(db.String(32), nullable=False)
    difficulty = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    xp_earned = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class DailyAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    challenge_date = db.Column(db.Date, nullable=False)
    score = db.Column(db.Integer, default=0, nullable=False)
    correct_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "challenge_date", name="uq_daily_user_date"),)


class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    achievement_key = db.Column(db.String(48), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "achievement_key", name="uq_user_achievement"),)


ACHIEVEMENTS = {
    "first_steps": ("First Steps", "Complete your first training session", "✦"),
    "ten_sessions": ("Getting Consistent", "Complete 10 training sessions", "⚡"),
    "fifty_sessions": ("Mind Athlete", "Complete 50 training sessions", "🏅"),
    "xp_100": ("XP Collector", "Earn 100 total XP", "💠"),
    "xp_500": ("XP Machine", "Earn 500 total XP", "💎"),
    "streak_3": ("Three-Day Spark", "Train on 3 consecutive days", "🔥"),
    "streak_7": ("Weekly Warrior", "Train on 7 consecutive days", "🌟"),
    "streak_30": ("Unstoppable", "Train on 30 consecutive days", "👑"),
    "daily_3": ("Daily Explorer", "Complete 3 daily brain tests", "🧠"),
    "daily_7": ("Daily Champion", "Complete 7 daily brain tests", "🏆"),
    "all_modes": ("Well-Rounded", "Play all five training modes", "🎯"),
    "level_5": ("Level Climber", "Reach player level 5", "🚀"),
}

MODE_TITLES = {
    "memory": ["Digit Echo", "Pattern Keeper", "Sequence Sprint", "Hidden Order", "Memory Ladder", "Double Recall", "Long Chain", "Flash Recall", "Deep Sequence", "Rapid Memory", "Master Recall", "Limit Break"],
    "reaction": ["Green Flash", "Quick Trigger", "Signal Snap", "Reflex Rush", "Rapid Response", "Split-Second", "Flash Point", "Velocity Test", "Precision Tap", "Reflex Storm", "Instant Impact", "Speed Trial"],
    "logic": ["Number Steps", "Missing Link", "Pattern Shift", "Square Route", "Sequence Rule", "Logic Switch", "Odd Pattern", "Growing Gap", "Number Matrix", "Rule Breaker", "Deep Deduction", "Logic Master"],
    "focus": ["Target Finder", "Signal Search", "Visual Filter", "Noise Control", "Crowded Field", "Focus Lock", "Visual Sprint", "Signal Scan", "Precision Grid", "Attention Test", "Focus Under Fire", "Clarity Trial"],
    "math": ["Quick Add", "Number Dash", "Multiply Fast", "Mental Sprint", "Mixed Steps", "Rapid Divide", "Calculation Grid", "Number Pressure", "Mental Gym", "Fast Equation", "Math Surge", "Calculation Master"],
}
GAME_KEYS = tuple(MODE_TITLES.keys())


def challenge_catalog():
    result = []
    for game, titles in MODE_TITLES.items():
        for level, title in enumerate(titles, 1):
            result.append({
                "id": f"{game}-{level:02d}", "game": game, "level": level,
                "title": title, "skill": game.title(),
                "description": f"Level {level} {game} challenge. The pace and complexity scale with your progress.",
            })
    return result


with app.app_context():
    db.create_all()
    # Add columns introduced after the original starter version, without deleting existing progress.
    inspector = inspect(db.engine)
    user_columns = {col["name"] for col in inspector.get_columns("user")}
    migrations = {
        "is_admin": "BOOLEAN NOT NULL DEFAULT FALSE",
        "current_streak": "INTEGER NOT NULL DEFAULT 0",
        "longest_streak": "INTEGER NOT NULL DEFAULT 0",
        "last_play_date": "DATE",
    }
    round_columns = {col["name"] for col in inspector.get_columns("round_result")}
    with db.engine.begin() as conn:
        for column, sql_type in migrations.items():
            if column not in user_columns:
                conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {column} {sql_type}'))
        if "xp_earned" not in round_columns:
            conn.execute(text('ALTER TABLE "round_result" ADD COLUMN xp_earned INTEGER NOT NULL DEFAULT 0'))

    admin_name = os.environ.get("ADMIN_USERNAME", "").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if admin_name and admin_name.replace("_", "").isalnum() and 3 <= len(admin_name) <= 24 and len(admin_password) >= 12:
        admin = User.query.filter(func.lower(User.username) == admin_name.lower()).first()
        if not admin:
            admin = User(username=admin_name, password_hash=generate_password_hash(admin_password), is_admin=True)
            db.session.add(admin)
        else:
            admin.is_admin = True
        db.session.commit()


def active_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not active_user():
            return jsonify(error="Please sign in to continue."), 401
        return fn(*args, **kwargs)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = active_user()
        if not user:
            return jsonify(error="Please sign in."), 401
        if not user.is_admin:
            return jsonify(error="Administrator access required."), 403
        return fn(*args, **kwargs)
    return wrapped


def local_today():
    tz_name = session.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def unlock_achievements(user):
    unlocked = {a.achievement_key for a in UserAchievement.query.filter_by(user_id=user.id).all()}
    daily_count = DailyAttempt.query.filter_by(user_id=user.id).count()
    played_modes = {r[0] for r in db.session.query(RoundResult.game).filter_by(user_id=user.id).distinct().all()}
    checks = {
        "first_steps": user.rounds_completed >= 1,
        "ten_sessions": user.rounds_completed >= 10,
        "fifty_sessions": user.rounds_completed >= 50,
        "xp_100": user.total_xp >= 100,
        "xp_500": user.total_xp >= 500,
        "streak_3": user.current_streak >= 3,
        "streak_7": user.current_streak >= 7,
        "streak_30": user.current_streak >= 30,
        "daily_3": daily_count >= 3,
        "daily_7": daily_count >= 7,
        "all_modes": set(GAME_KEYS).issubset(played_modes),
        "level_5": user.total_xp >= 400,
    }
    newly = []
    for key, achieved in checks.items():
        if achieved and key not in unlocked:
            db.session.add(UserAchievement(user_id=user.id, achievement_key=key))
            newly.append(key)
    return newly


def user_achievement_payload(user):
    got = {a.achievement_key: a.unlocked_at for a in UserAchievement.query.filter_by(user_id=user.id).all()}
    return [
        {"key": key, "title": meta[0], "description": meta[1], "icon": meta[2],
         "unlocked": key in got, "unlocked_at": got[key].strftime("%d %b %Y") if key in got else None}
        for key, meta in ACHIEVEMENTS.items()
    ]


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/timezone")
def set_timezone():
    data = request.get_json(silent=True) or {}
    name = str(data.get("timezone", "UTC"))[:64]
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        name = "UTC"
    session["timezone"] = name
    return jsonify(ok=True, timezone=name)


@app.get("/api/me")
def me():
    user = active_user()
    if not user:
        return jsonify(logged_in=False)
    today = local_today()
    recent = (RoundResult.query.filter_by(user_id=user.id)
              .order_by(RoundResult.created_at.desc()).limit(8).all())
    daily_done = DailyAttempt.query.filter_by(user_id=user.id, challenge_date=today).first() is not None
    return jsonify(
        logged_in=True, username=user.username, is_admin=user.is_admin,
        xp=user.total_xp, level=user.total_xp // 100 + 1,
        best_round=user.best_round, rounds=user.rounds_completed,
        current_streak=user.current_streak, longest_streak=user.longest_streak,
        daily_done=daily_done, timezone=session.get("timezone", "UTC"),
        achievements=user_achievement_payload(user),
        recent=[{"game": r.game, "score": r.score, "difficulty": r.difficulty,
                 "xp": r.xp_earned, "date": r.created_at.strftime("%d %b")} for r in recent],
    )


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if len(username) < 3 or len(username) > 24 or not username.replace("_", "").isalnum():
        return jsonify(error="Username must be 3–24 characters (letters, numbers, underscore)."), 400
    if len(password) < 8 or len(password) > 128:
        return jsonify(error="Password must be between 8 and 128 characters."), 400
    if User.query.filter(func.lower(User.username) == username.lower()).first():
        return jsonify(error="That username is already taken."), 409
    user = User(username=username, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    return jsonify(ok=True)


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = User.query.filter(func.lower(User.username) == username.lower()).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify(error="Incorrect username or password."), 401
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    return jsonify(ok=True)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.post("/api/complete")
@login_required
def complete():
    user = active_user()
    data = request.get_json(silent=True) or {}
    game = str(data.get("game", ""))
    if game not in (*GAME_KEYS, "daily"):
        return jsonify(error="Unknown training mode."), 400
    try:
        difficulty = int(data.get("difficulty", 1))
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        return jsonify(error="Invalid result."), 400
    difficulty = max(1, min(12, difficulty))
    score = max(0, min(3000, score))
    today = local_today()

    if user.last_play_date is None or user.last_play_date < today - timedelta(days=1):
        user.current_streak = 1
    elif user.last_play_date == today - timedelta(days=1):
        user.current_streak += 1
    user.last_play_date = today
    user.longest_streak = max(user.longest_streak, user.current_streak)

    base_xp = max(5, min(120, score // 12 + difficulty * 2))
    daily_bonus = 0
    if game == "daily" and not DailyAttempt.query.filter_by(user_id=user.id, challenge_date=today).first():
        try:
            correct = max(0, min(5, int(data.get("correct_count", 0))))
        except (TypeError, ValueError):
            correct = 0
        db.session.add(DailyAttempt(user_id=user.id, challenge_date=today, score=score, correct_count=correct))
        daily_bonus = 40
    xp_earned = base_xp + daily_bonus
    result = RoundResult(user_id=user.id, game=game, difficulty=difficulty, score=score, xp_earned=xp_earned)
    user.total_xp += xp_earned
    user.rounds_completed += 1
    user.best_round = max(user.best_round, difficulty)
    db.session.add(result)
    newly = unlock_achievements(user)
    db.session.commit()
    return jsonify(ok=True, xp_earned=xp_earned, daily_bonus=daily_bonus,
                   total_xp=user.total_xp, rounds=user.rounds_completed,
                   current_streak=user.current_streak, newly_unlocked=newly)


@app.get("/api/challenges")
def challenges():
    return jsonify(total=60, challenges=challenge_catalog())


@app.get("/api/daily")
@login_required
def daily():
    today = local_today()
    attempt = DailyAttempt.query.filter_by(user_id=active_user().id, challenge_date=today).first()
    seed = int(today.strftime("%Y%m%d"))
    # The daily route stays the same for every player on a given calendar day.
    daily_games = list(GAME_KEYS)
    offset = seed % len(daily_games)
    daily_games = daily_games[offset:] + daily_games[:offset]
    daily_tasks = []
    for game in daily_games:
        level = (seed // (len(daily_tasks) + 3)) % 8 + 1
        template = MODE_TITLES[game][level - 1]
        daily_tasks.append({"game": game, "level": level, "title": template})
    return jsonify(date=today.isoformat(), completed=attempt is not None,
                   score=attempt.score if attempt else None, tasks=daily_tasks)


@app.get("/api/leaderboard")
def leaderboard():
    users = (User.query.filter_by(is_admin=False)
             .order_by(User.total_xp.desc(), User.rounds_completed.desc(), User.username.asc())
             .limit(50).all())
    return jsonify(entries=[{"rank": i + 1, "username": u.username, "xp": u.total_xp,
                             "level": u.total_xp // 100 + 1, "rounds": u.rounds_completed}
                            for i, u in enumerate(users)])


@app.get("/api/analytics")
@login_required
def analytics():
    user = active_user()
    since = datetime.utcnow() - timedelta(days=13)
    rows = RoundResult.query.filter(RoundResult.user_id == user.id, RoundResult.created_at >= since).all()
    days = {}
    by_game = {}
    for i in range(14):
        d = (date.today() - timedelta(days=13 - i)).strftime("%d %b")
        days[d] = {"date": d, "rounds": 0, "score": 0}
    for r in rows:
        key = r.created_at.strftime("%d %b")
        if key in days:
            days[key]["rounds"] += 1
            days[key]["score"] += r.score
        slot = by_game.setdefault(r.game, {"game": r.game, "rounds": 0, "score": 0, "xp": 0})
        slot["rounds"] += 1
        slot["score"] += r.score
        slot["xp"] += r.xp_earned
    for slot in by_game.values():
        slot["average_score"] = round(slot["score"] / slot["rounds"], 1)
    all_count = user.rounds_completed
    return jsonify(total_rounds=all_count, total_xp=user.total_xp,
                   average_score=round(sum(r.score for r in rows) / len(rows), 1) if rows else 0,
                   best_score=max((r.score for r in rows), default=0),
                   daily=[days[k] for k in days], by_game=list(by_game.values()))


@app.get("/api/admin/stats")
@admin_required
def admin_stats():
    total_users = User.query.filter_by(is_admin=False).count()
    active_today = User.query.filter(User.is_admin.is_(False), User.last_play_date == local_today()).count()
    total_rounds = RoundResult.query.count()
    total_xp = db.session.query(func.coalesce(func.sum(User.total_xp), 0)).filter_by(is_admin=False).scalar()
    latest = (RoundResult.query.order_by(RoundResult.created_at.desc()).limit(12).all())
    recent = []
    for row in latest:
        user = db.session.get(User, row.user_id)
        recent.append({"username": user.username if user else "Deleted user", "game": row.game,
                       "score": row.score, "date": row.created_at.strftime("%d %b %H:%M")})
    top = (User.query.filter_by(is_admin=False).order_by(User.total_xp.desc()).limit(10).all())
    return jsonify(total_users=total_users, active_today=active_today, total_rounds=total_rounds,
                   total_xp=int(total_xp or 0), recent=recent,
                   top=[{"username": u.username, "xp": u.total_xp, "rounds": u.rounds_completed} for u in top])


@app.get("/health")
def health():
    return jsonify(status="ok", service="neuroquest")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
