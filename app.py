from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_SECRET_KEY"
DB = Path(__file__).with_name("makerspace.db")

FILAMENTS = ["PLA", "PETG", "ABS", "ASA", "TPU", "Nylon", "Other"]

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        filament TEXT NOT NULL DEFAULT 'PLA',
        status TEXT NOT NULL DEFAULT 'available',
        current_user_id INTEGER,
        started_at TEXT,
        estimated_end TEXT,
        FOREIGN KEY(current_user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        printer_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        FOREIGN KEY(printer_id) REFERENCES printers(id),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    if conn.execute("SELECT COUNT(*) FROM printers").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO printers (name, filament) VALUES (?, ?)",
            [("Printer 1", "PLA"), ("Printer 2", "PLA"), ("Printer 3", "PETG")]
        )
    conn.commit()
    conn.close()

def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    conn.close()
    return user

def update_expired_prints():
    conn = db()
    now = datetime.now()
    rows = conn.execute("""
        SELECT id, estimated_end FROM printers
        WHERE status='in use' AND estimated_end IS NOT NULL
    """).fetchall()

    for row in rows:
        try:
            end = datetime.fromisoformat(row["estimated_end"])
            if end <= now:
                conn.execute("""
                    UPDATE printers
                    SET status='available', current_user_id=NULL,
                        started_at=NULL, estimated_end=NULL
                    WHERE id=?
                """, (row["id"],))
        except ValueError:
            pass

    # Reservations that have passed their end time are removed.
    conn.execute("DELETE FROM reservations WHERE end_time <= ?", (now.isoformat(),))
    conn.commit()
    conn.close()

@app.route("/")
def index():
    if not current_user():
        return redirect(url_for("login"))

    update_expired_prints()
    conn = db()
    printers = conn.execute("""
        SELECT p.*, u.username
        FROM printers p
        LEFT JOIN users u ON p.current_user_id = u.id
        ORDER BY p.id
    """).fetchall()

    reservations = conn.execute("""
        SELECT r.*, p.name AS printer_name, u.username
        FROM reservations r
        JOIN printers p ON p.id = r.printer_id
        JOIN users u ON u.id = r.user_id
        ORDER BY r.start_time
    """).fetchall()
    conn.close()

    return render_template(
        "index.html",
        printers=printers,
        reservations=reservations,
        filaments=FILAMENTS,
        user=current_user()
    )

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("register"))

        conn = db()
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(password))
            )
            conn.commit()
            session["user_id"] = cur.lastrowid
            return redirect(url_for("index"))
        except sqlite3.IntegrityError:
            flash("That username is already taken.", "error")
            return redirect(url_for("register"))
        finally:
            conn.close()

    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("index"))

        flash("Invalid username or password.", "error")

    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.post("/printer/<int:printer_id>/filament")
def set_filament(printer_id):
    if not current_user():
        return redirect(url_for("login"))

    filament = request.form["filament"]
    if filament not in FILAMENTS:
        flash("Invalid filament.", "error")
        return redirect(url_for("index"))

    conn = db()
    conn.execute("UPDATE printers SET filament=? WHERE id=?", (filament, printer_id))
    conn.commit()
    conn.close()
    flash("Filament updated.", "success")
    return redirect(url_for("index"))

@app.post("/printer/<int:printer_id>/start")
def start_print(printer_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    try:
        minutes = int(request.form["minutes"])
        if minutes < 1 or minutes > 10080:
            raise ValueError
    except ValueError:
        flash("Enter an estimated print time between 1 minute and 7 days.", "error")
        return redirect(url_for("index"))

    update_expired_prints()
    conn = db()
    printer = conn.execute("SELECT * FROM printers WHERE id=?", (printer_id,)).fetchone()

    if not printer:
        flash("Printer not found.", "error")
    elif printer["status"] != "available":
        flash("That printer is not currently available.", "error")
    else:
        now = datetime.now()
        end = now + timedelta(minutes=minutes)
        conn.execute("""
            UPDATE printers
            SET status='in use', current_user_id=?, started_at=?, estimated_end=?
            WHERE id=?
        """, (user["id"], now.isoformat(), end.isoformat(), printer_id))
        conn.commit()
        flash(f"{printer['name']} is now marked as in use.", "success")

    conn.close()
    return redirect(url_for("index"))

@app.post("/printer/<int:printer_id>/release")
def release_printer(printer_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    conn = db()
    printer = conn.execute("SELECT * FROM printers WHERE id=?", (printer_id,)).fetchone()

    if printer and (printer["current_user_id"] == user["id"]):
        conn.execute("""
            UPDATE printers
            SET status='available', current_user_id=NULL,
                started_at=NULL, estimated_end=NULL
            WHERE id=?
        """, (printer_id,))
        conn.commit()
        flash("Printer released.", "success")
    else:
        flash("You can only release a printer you are currently using.", "error")

    conn.close()
    return redirect(url_for("index"))

@app.post("/printer/<int:printer_id>/reserve")
def reserve_printer(printer_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    try:
        start = datetime.fromisoformat(request.form["start_time"])
        minutes = int(request.form["minutes"])
        if minutes < 1 or minutes > 10080:
            raise ValueError
    except ValueError:
        flash("Enter a valid future start time and duration.", "error")
        return redirect(url_for("index"))

    now = datetime.now()
    if start <= now:
        flash("Reservations must start in the future.", "error")
        return redirect(url_for("index"))

    end = start + timedelta(minutes=minutes)

    conn = db()
    printer = conn.execute("SELECT * FROM printers WHERE id=?", (printer_id,)).fetchone()

    conflict = conn.execute("""
        SELECT 1 FROM reservations
        WHERE printer_id=?
          AND start_time < ?
          AND end_time > ?
    """, (printer_id, end.isoformat(), start.isoformat())).fetchone()

    # Also prevent reserving over a currently active print.
    active_conflict = False
    if printer and printer["status"] == "in use" and printer["estimated_end"]:
        active_end = datetime.fromisoformat(printer["estimated_end"])
        active_conflict = start < active_end

    if not printer:
        flash("Printer not found.", "error")
    elif conflict or active_conflict:
        flash("That time overlaps an existing reservation or print.", "error")
    else:
        conn.execute("""
            INSERT INTO reservations (printer_id, user_id, start_time, end_time)
            VALUES (?, ?, ?, ?)
        """, (printer_id, user["id"], start.isoformat(), end.isoformat()))
        conn.commit()
        flash("Printer reserved.", "success")

    conn.close()
    return redirect(url_for("index"))

@app.post("/reservation/<int:reservation_id>/cancel")
def cancel_reservation(reservation_id):
    user = current_user()
    if not user:
        return redirect(url_for("login"))

    conn = db()
    conn.execute(
        "DELETE FROM reservations WHERE id=? AND user_id=?",
        (reservation_id, user["id"])
    )
    conn.commit()
    conn.close()
    flash("Reservation cancelled.", "success")
    return redirect(url_for("index"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
