from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

import os
from datetime import datetime, timedelta, timezone, time
import sqlite3

# ========================
# applied_jobs table
# ========================

conn = sqlite3.connect("jobs.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS applied_jobs (
    user_id INTEGER,
    company TEXT,
    role TEXT,
    applied_at TEXT,
    UNIQUE(user_id, company, role)
)
""")
conn.commit()

# ========================
# DB MIGRATION (ONE-TIME SAFE)
# ========================

cursor.execute("PRAGMA table_info(applied_jobs)")
columns = [c[1] for c in cursor.fetchall()]

if "followup_after" not in columns:
    cursor.execute(
        "ALTER TABLE applied_jobs ADD COLUMN followup_after INTEGER DEFAULT 5"
    )

if "link" not in columns:
    cursor.execute(
        "ALTER TABLE applied_jobs ADD COLUMN link TEXT"
    )

conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_skills (
    user_id INTEGER PRIMARY KEY,
    skills TEXT,
    location TEXT DEFAULT 'india',
    exp_min INTEGER DEFAULT 0,
    exp_max INTEGER DEFAULT 30,
    work_mode TEXT
)
""")
conn.commit()

# cursor.execute("""
# ALTER TABLE user_skills
# ADD COLUMN active INTEGER DEFAULT 1
# """)
# conn.commit()
cursor.execute("PRAGMA table_info(user_skills)")
columns = [c[1] for c in cursor.fetchall()]
if "active" not in columns:
    cursor.execute("ALTER TABLE user_skills ADD COLUMN active INTEGER DEFAULT 1")
    conn.commit()


# ==========================
# CONFIG
# ==========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ==========================
# COMMAND HANDLERS
# ==========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        INSERT INTO user_skills (user_id, active)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO UPDATE SET active = 1
    """, (user_id,))
    conn.commit()

    await update.message.reply_text(
        "✅ Job notifications enabled.\n"
        "Use /skills to set your role."
    )

async def set_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Usage:\n/skills AWS DevOps Engineer"
        )
        return

    skills = " ".join(context.args)
    user_id = update.effective_user.id

    cursor.execute(
        "SELECT skills FROM user_skills WHERE user_id = ?",
        (user_id,)
    )
    existing = cursor.fetchone()

    if existing:
        await update.message.reply_text(
            "⚠️ Skills already set.\n"
            "Use /update_skill <new skills>"
        )
        return

    cursor.execute(
        "INSERT INTO user_skills (user_id, skills, active) VALUES (?, ?, 1)",
        (user_id, skills)
    )
    conn.commit()

    await update.message.reply_text(
        f"✅ Skills saved:\n{skills}"
    )

async def my_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute(
        "SELECT skills FROM user_skills WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text(
            "❌ No skills set yet.\nUse /skills <role>"
        )
        return

    await update.message.reply_text(
        f"🧠 Your current role:\n✅ {row[0]}"
    )

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute(
        "SELECT skills FROM user_skills WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    skills = row[0] if row else "your skills"

    await update.message.reply_text(
        "⏰ JOB REMINDER\n\n"
        f"Skills: {skills}\n\n"
        "✔ Apply to 3 matching jobs\n"
        "✔ Best time: 8–10 AM\n"
        "✔ Use LinkedIn & Naukri\n"
        "✔ Message 1 recruiter today"
    )

async def hrmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📩 HR / Recruiter Message Template:\n\n"
        "Hi {{Name}},\n"
        "I hope you are doing well.\n\n"
        "I’m a Cloud/DevOps Engineer with 4+ years of experience in AWS, "
        "CI/CD, Docker, and automation.\n\n"
        "I’m interested in the {{Role}} position and would love to connect.\n\n"
        "Thanks & regards,\n"
        "{{Your Name}}"
    )

async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT skills, location, exp_min, exp_max, work_mode
        FROM user_skills WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text("❌ Set skills first using /skills")
        return

    skills, location, exp_min, exp_max, work_mode = row
    link = naukri_search_url(skills, location, exp_min, exp_max, work_mode)
    await update.message.reply_text(f"🔍 Jobs for you:\n{link}")

async def applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Usage:\n"
            "/applied <Company> <Role> [days=7] [link=URL]"
        )
        return

    company = context.args[0]
    role_words = []
    days = 5
    link = None

    for arg in context.args[1:]:
        if arg.startswith("days="):
            try:
                days = int(arg.split("=", 1)[1])
            except ValueError:
                await update.message.reply_text("❌ days must be a number")
                return
        elif arg.startswith("link="):
            link = arg.split("=", 1)[1]
        else:
            role_words.append(arg)

    if not role_words:
        await update.message.reply_text("❌ Role is required")
        return

    role = " ".join(role_words)
    user_id = update.effective_user.id

    cursor.execute("""
        INSERT INTO applied_jobs
        (user_id, company, role, applied_at, followup_after, link)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        company,
        role,
        datetime.now(timezone.utc).isoformat(),
        days,
        link
    ))
    conn.commit()

    await update.message.reply_text(
        f"✅ Saved: {company} – {role}\n"
        f"⏰ Follow-up in {days} day(s)"
        + (f"\n🔗 {link}" if link else "")
    )

async def followups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT company, role, applied_at, followup_after, link
        FROM applied_jobs
        WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 No follow-ups pending")
        return

    now = datetime.now(timezone.utc)
    msg = "🔔 FOLLOW-UP REMINDERS:\n\n"
    due = False

    for company, role, applied_at, followup_after, link in rows:
        applied_time = datetime.fromisoformat(applied_at)
        if applied_time.tzinfo is None:
            applied_time = applied_time.replace(tzinfo=timezone.utc)

        if now - applied_time >= timedelta(days=followup_after):
            due = True
            msg += (
                f"📌 {company} – {role}\n"
                f"➡ Follow-up now\n"
                + (f"🔗 {link}\n" if link else "")
                + "\n"
            )
    if not due:
        msg = "✅ No follow-ups due today"

    await update.message.reply_text(msg)

async def followupmsg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi {{Name}},\n\n"
        "Following up on my application for {{Role}} at {{Company}}.\n"
        "I’d love to know if there’s any update.\n\n"
        "Thanks,\n{{Your Name}}"
    )

async def daily_followup(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT a.user_id, a.company, a.role, a.applied_at
        FROM applied_jobs a
        JOIN user_skills u ON a.user_id = u.user_id
        WHERE u.active = 1
    """)
    rows = cursor.fetchall()

    reminders = {}

    for user_id, company, role, applied_at in rows:
        applied_time = datetime.fromisoformat(applied_at)
        if applied_time.tzinfo is None:
            applied_time = applied_time.replace(tzinfo=timezone.utc)

        # TEMP: 1 minute for testing (change to days=5 later)
        if datetime.now(timezone.utc) - applied_time >= timedelta(days=5):
            reminders.setdefault(user_id, []).append(
                f"📌 Follow up: {company} – {role}"
            )

    for user_id, msgs in reminders.items():
        await context.bot.send_message(
            chat_id=user_id,
            text="🔔 Follow-up Reminder\n\n" + "\n".join(msgs)

        )

async def daily_jobs(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("""
        SELECT user_id, skills, location, exp_min, exp_max, work_mode
        FROM user_skills
        WHERE active = 1
    """)
    users = cursor.fetchall()

    for user_id, skills, location, exp_min, exp_max, work_mode in users:
        link = naukri_search_url(skills, location, exp_min, exp_max, work_mode)

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "🔥 New jobs matching your profile\n\n"
                f"🔍 Role: {skills}\n"
                f"📍 Location: {location}\n"
                f"🧠 Experience: {exp_min}-{exp_max} yrs\n"
                f"🏢 Mode: {work_mode or 'Any'}\n\n"
                f"👉 {link}\n\n"
                "Tip: Apply to 3–5 jobs today"
            )
        )

async def update_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Usage:\n/update_skill AWS DevOps Engineer"
        )
        return

    skills = " ".join(context.args)
    user_id = update.effective_user.id

    cursor.execute(
        "UPDATE user_skills SET skills = ? WHERE user_id = ?",
        (skills, user_id)
    )
    conn.commit()

    if cursor.rowcount == 0:
        await update.message.reply_text(
            "❌ No existing skills found.\nUse /skills first."
        )
        return

    await update.message.reply_text(
        f"🔄 Skills updated:\n✅ {skills}"
    )

# async def weekly_summary(context: ContextTypes.DEFAULT_TYPE):
#     one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

#     cursor.execute("""
#         SELECT user_id, action, COUNT(*)
#         FROM job_actions
#         WHERE action_at >= ?
#         GROUP BY user_id, action
#     """, (one_week_ago.isoformat(),))

#     rows = cursor.fetchall()

#     summary = {}

#     for user_id, action, count in rows:
#         summary.setdefault(user_id, {"apply": 0, "follow": 0, "ignore": 0})
#         summary[user_id][action] += count

#     for user_id, data in summary.items():
#         msg = (
#             "📊 Weekly Job Summary\n\n"
#             f"✅ Applied: {data['apply']}\n"
#             f"🔔 Followed up: {data['follow']}\n"
#             f"❌ Ignored: {data['ignore']}"
#         )

#         await context.bot.send_message(chat_id=user_id, text=msg)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute(
        "UPDATE user_skills SET active = 0 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()

    await update.message.reply_text(
        "⛔ Job notifications stopped.\n"
        "Use /start again to resume."
    )


async def preferences(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    prefs = {}
    for arg in context.args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            prefs[k.lower()] = v.lower()

    location = prefs.get("location")
    exp = prefs.get("exp")
    mode = prefs.get("mode")

    if exp and "-" in exp:
        exp_min, exp_max = exp.split("-", 1)
    else:
        exp_min = exp_max = None

    if mode:
        if mode in ["remote"]:
            mode = "remote"
        elif mode in ["hybrid"]:
            mode = "hybrid"
        elif mode in ["office", "wfo"]:
            mode = "office"
        else:
            await update.message.reply_text(
                "❌ Invalid mode.\n"
                "Use one of: remote | hybrid | office"
            )
            return

    cursor.execute("""
        UPDATE user_skills
        SET location = ?, exp_min = ?, exp_max = ?, work_mode = ?
        WHERE user_id = ?
    """, (location, exp_min, exp_max, mode, user_id))
    conn.commit()

    if cursor.rowcount == 0:
        await update.message.reply_text(
            "❌ No profile found.\nUse /skills first."
        )
        return

    await update.message.reply_text(
        "✅ Preferences saved:\n"
        f"📍 Location: {location or 'Any'}\n"
        f"🧠 Experience: {exp or 'Any'}\n"
        f"🏢 Mode: {mode or 'Any'}"
    )

async def remove_applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "❌ Usage:\n"
            "/remove_applied <Company> <Role>\n"
            "or\n"
            "/remove_applied all"
        )
        return

    # Remove all
    if context.args[0].lower() == "all":
        cursor.execute(
            "DELETE FROM applied_jobs WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()

        await update.message.reply_text("🗑️ All reminders removed")
        return

    company = context.args[0]
    role = " ".join(context.args[1:])

    cursor.execute("""
        DELETE FROM applied_jobs
        WHERE user_id = ?
          AND LOWER(company) = LOWER(?)
          AND LOWER(role) = LOWER(?)
    """, (user_id, company, role))
    conn.commit()

    if cursor.rowcount == 0:
        await update.message.reply_text(
            "⚠️ No matching reminder found.\n"
            "Tip: use /list_applied to see exact names."
        )
    else:
        await update.message.reply_text(
            f"🗑️ Reminder removed:\n{company} – {role}"
        )

async def list_applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT company, role, followup_after, link
        FROM applied_jobs
        WHERE user_id = ?
        ORDER BY applied_at DESC
    """, (user_id,))
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text(
            "📭 You have not added any applied jobs yet"
        )
        return

    msg = "📄 Your applied jobs:\n\n"
    for idx, (company, role, days, link) in enumerate(rows, start=1):
        msg += (
            f"{idx}️⃣ {company} – {role}\n"
            f"⏰ Follow-up after {days} day(s)\n"
        )
        if link:
            msg += f"🔗 {link}\n"
        msg += "\n"

    await update.message.reply_text(msg)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute("""
        SELECT skills, location, exp_min, exp_max, work_mode, active
        FROM user_skills
        WHERE user_id = ?
    """, (user_id,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text(
            "❌ No profile found.\nUse /start and /skills first."
        )
        return

    skills, location, exp_min, exp_max, work_mode, active = row

    cursor.execute(
        "SELECT COUNT(*) FROM applied_jobs WHERE user_id = ?",
        (user_id,)
    )
    applied_count = cursor.fetchone()[0]

    now = datetime.now(timezone.utc)
    cursor.execute("""
        SELECT COUNT(*) FROM applied_jobs
        WHERE user_id = ?
          AND (? - julianday(applied_at)) * 1 >= followup_after
    """, (user_id, now.isoformat()))
    due_count = cursor.fetchone()[0]

    await update.message.reply_text(
        "📊 Your Job Bot Status\n\n"
        f"🔔 Alerts: {'ON' if active else 'OFF'}\n"
        f"🔍 Role: {skills}\n\n"
        f"📍 Location: {location}\n"
        f"🧠 Experience: {exp_min}-{exp_max} yrs\n"
        f"🏢 Work mode: {work_mode or 'Any'}\n\n"
        f"📌 Applied jobs tracked: {applied_count}\n"
        f"⏰ Follow-ups due today: {due_count}"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Job Seeker Bot – Help\n\n"

        "🔔 JOB ALERTS\n"
        "/start – Enable daily job alerts\n"
        "/stop – Stop job alerts\n"
        "/jobs – Get job links now\n\n"

        "📘 MANUAL – HOW TO USE THE BOT\n\n"
        "1️⃣ Set your role (one time):\n"
        "/skills AWS DevOps Engineer\n"
        "/my_skills – View your current role\n"
        "/update_skill AWS DevOps Cloud Engineer – Update your role\n\n"

        "2️⃣ Set job preferences (optional):\n"
        "/preferences location=bangalore exp=4-6 mode=hybrid\n\n"

        "3️⃣ Get job links:\n"
        "/jobs\n"
        "👉 Click the link and apply manually\n\n"

        "4️⃣ Save applied job for follow-up:\n"
        "/applied Amazon DevOps Engineer days=7 link=https://job-link\n\n"

        "5️⃣ View applied jobs:\n"
        "/list_applied\n\n"

        "6️⃣ Check follow-ups:\n"
        "/followups\n\n"

        "7️⃣ Remove reminder if needed:\n"
        "/remove_applied Amazon DevOps Engineer\n"
        "/remove_applied all\n\n"

        "8️⃣ Pause / resume alerts:\n"
        "/stop\n"
        "/start\n\n"

        "✅ Tip: The bot never auto-applies. You stay in control."

        "ℹ️ OTHER\n"
        "/status – Show your current settings and reminders\n"
        "/help – Show this help message"
    )

def naukri_search_url(skills, location, exp_min, exp_max, work_mode=None):
    if not skills:
        return None
    keyword = skills.lower().replace(" ", "-")
    url = f"https://www.naukri.com/{keyword}-jobs-in-{location}"

    params = [f"experience={exp_min}-{exp_max}"]

    if work_mode:
        params.append(f"wfhType={work_mode}")

    return url + "?" + "&".join(params)

# ==========================
# MAIN APP
# ==========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ------------------
    # Command handlers
    # ------------------
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skills", set_skills))
    app.add_handler(CommandHandler("update_skill", update_skill))
    app.add_handler(CommandHandler("my_skills", my_skills))
    app.add_handler(CommandHandler("preferences", preferences))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("applied", applied))
    app.add_handler(CommandHandler("followups", followups))
    app.add_handler(CommandHandler("remove_applied", remove_applied))
    app.add_handler(CommandHandler("list_applied", list_applied))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("hep", help_cmd))
    app.add_handler(CommandHandler("status", status))

    # ------------------
    # Scheduler logic
    # ------------------
    if os.getenv("GITHUB_ACTIONS") == "true":
        # CI/CD mode
        app.job_queue.run_daily(daily_jobs, time=time(hour=9))
        app.job_queue.run_daily(daily_followup, time=time(hour=9))
    else:
        # Local testing / always-on hosting
        app.job_queue.run_repeating(daily_jobs, interval=120, first=10)
        app.job_queue.run_repeating(daily_followup, interval=300, first=20)

    print("🤖 Job Seeker Bot running")

    app.run_polling(stop_signals=None)

if __name__ == "__main__":
    main()
