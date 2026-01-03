from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes

)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import os
from datetime import datetime, timedelta, timezone, time
import sqlite3
import hashlib

# ========================
# Connecting to sqlite3 Db
# ========================

conn = sqlite3.connect("jobs.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS applied_jobs (
    user_id INTEGER,
    company TEXT,
    role TEXT,
    applied_at TEXT
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS user_skills (
    user_id INTEGER PRIMARY KEY,
    skills TEXT
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS sent_jobs (
    user_id INTEGER,
    job_id TEXT,
    sent_at TEXT,
    PRIMARY KEY (user_id, job_id)
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS job_actions (
    user_id INTEGER,
    job_id TEXT,
    action TEXT,
    action_at TEXT
)
""")
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
    await update.message.reply_text(
        "👋 Welcome to Job Seeker Bot\n\n"
        "Commands:\n"
        "/skills <your skills>\n"
        "/remind\n"
        "/hrmsg\n"
    )

async def set_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: /skills AWS DevOps Docker")
        return

    user_id = update.effective_user.id

    cursor.execute(
        "SELECT skills FROM user_skills WHERE user_id = ?",
        (user_id,)
    )
    if cursor.fetchone():
        await update.message.reply_text(
            "⚠️ Skills already set.\n"
            "Use /update_skill <new skills> to update."
        )
        return

    skills_text = " ".join(context.args)
    cursor.execute(
        "INSERT INTO user_skills (user_id, skills) VALUES (?, ?)",
        (user_id, skills_text)
    )
    conn.commit()

    await update.message.reply_text("✅ Skills saved permanently")


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

    cursor.execute(
        "SELECT skills FROM user_skills WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text("❌ Set skills first using /skills")
        return

    matches = match_jobs(row[0])
    if not matches:
        await update.message.reply_text("❌ No matching jobs today")
        return

    for _, job in matches:
        await update.message.reply_text(
            f"🔥 {job['title']} ({job['company']})\n{job['link']}"
        )


async def applied(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Usage: /applied <Company> <Role>"
        )
        return

    company = context.args[0]
    role = " ".join(context.args[1:])
    user_id = update.effective_user.id

    cursor.execute(
        "INSERT INTO applied_jobs VALUES (?, ?, ?, ?)",
        (user_id, company, role, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()

    await update.message.reply_text(
        f"✅ Saved.\nI’ll remind you to follow up in 5 days for:\n"
        f"{company} – {role}"
    )

async def followups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    cursor.execute(
        "SELECT company, role, applied_at FROM applied_jobs WHERE user_id = ?",
        (user_id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("📭 No follow-ups pending")
        return

    now = datetime.now(timezone.utc)
    msg = "🔔 FOLLOW-UP REMINDERS:\n\n"
    due = False

    for company, role, applied_at in rows:
        applied_time = datetime.fromisoformat(applied_at)
        if applied_time.tzinfo is None:
            applied_time = applied_time.replace(tzinfo=timezone.utc)
        if now - applied_time >= timedelta(days=5):
            due = True
            msg += f"📌 {company} – {role}\n➡ Send follow-up today\n\n"

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
    cursor.execute(
        "SELECT user_id, company, role, applied_at FROM applied_jobs"
    )
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

# async def daily_jobs(context: ContextTypes.DEFAULT_TYPE):
#     cursor.execute("SELECT user_id, skills FROM user_skills")
#     users = cursor.fetchall()

#     for user_id, skills in users:
#         matches = match_jobs(skills)
#         if not matches:
#             continue

#         for _, job in matches:
#             keyboard = [[
#                 InlineKeyboardButton(
#                     "✅ Apply",
#                     callback_data=f"apply|{job['company']}|{job['title']}"
#                 ),
#                 InlineKeyboardButton(
#                     "❌ Ignore",
#                     callback_data="ignore"
#                 )
#             ]]

#             await context.bot.send_message(
#                 chat_id=user_id,
#                 text=f"🔥 {job['title']} ({job['company']})\n🔗 {job['link']}",
#                 reply_markup=InlineKeyboardMarkup(keyboard)
#             )

async def daily_jobs(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id, skills FROM user_skills")
    users = cursor.fetchall()

    for user_id, skills in users:
        matches = match_jobs(skills)
        if not matches:
            continue

        for _, job in matches:
            job_id = get_job_id(job)

            # Check if already sent
            cursor.execute(
                "SELECT 1 FROM sent_jobs WHERE user_id = ? AND job_id = ?",
                (user_id, job_id)
            )
            if cursor.fetchone():
                continue  # already sent → skip

            keyboard = [[
                InlineKeyboardButton(
                    "✅ Apply",
                    callback_data=f"apply|{job['company']}|{job['title']}"
                ),
                InlineKeyboardButton(
                    "❌ Ignore",
                    callback_data="ignore"
                )
            ]]

            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔥 {job['title']} ({job['company']})\n🔗 {job['link']}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            # Mark as sent
            cursor.execute(
                "INSERT INTO sent_jobs VALUES (?, ?, ?)",
                (user_id, job_id, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        return

    action, company, role = query.data.split("|")
    user_id = query.from_user.id

    job_id = get_job_id({
        "company": company,
        "title": role,
        "link": ""
    })

    cursor.execute(
        "INSERT INTO job_actions VALUES (?, ?, ?, ?)",
        (user_id, job_id, action, datetime.now(timezone.utc).isoformat())
    )
    conn.commit()

    if action == "apply":
        await query.edit_message_text(f"✅ Applied noted for {company} – {role}")

    elif action == "follow":
        await query.edit_message_text(f"📩 Follow-up noted for {company} – {role}")

    else:
        await query.edit_message_text("❌ Ignored")

async def update_skill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /update_skill AWS DevOps Terraform"
        )
        return

    user_id = update.effective_user.id
    skills_text = " ".join(context.args)

    cursor.execute(
        "UPDATE user_skills SET skills = ? WHERE user_id = ?",
        (skills_text, user_id)
    )
    conn.commit()

    await update.message.reply_text("✅ Skills updated successfully")

async def weekly_summary(context: ContextTypes.DEFAULT_TYPE):
    one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    cursor.execute("""
        SELECT user_id, action, COUNT(*)
        FROM job_actions
        WHERE action_at >= ?
        GROUP BY user_id, action
    """, (one_week_ago.isoformat(),))

    rows = cursor.fetchall()

    summary = {}

    for user_id, action, count in rows:
        summary.setdefault(user_id, {"apply": 0, "follow": 0, "ignore": 0})
        summary[user_id][action] += count

    for user_id, data in summary.items():
        msg = (
            "📊 Weekly Job Summary\n\n"
            f"✅ Applied: {data['apply']}\n"
            f"🔔 Followed up: {data['follow']}\n"
            f"❌ Ignored: {data['ignore']}"
        )

        await context.bot.send_message(chat_id=user_id, text=msg)

# ==========================
# JOB MATCHING (SIMPLE)
# ==========================

# Sample job pool (later we can fetch real jobs)
JOBS = [
    {
        "title": "AWS DevOps Engineer",
        "company": "ABC Tech",
        "keywords": ["aws", "devops", "docker", "ci/cd"],
        "link": "https://example.com/job1"
    },
    {
        "title": "Cloud Engineer",
        "company": "XYZ Cloud",
        "keywords": ["aws", "cloud", "terraform"],
        "link": "https://example.com/job2"
    },
    {
        "title": "Automation Tester",
        "company": "TestCorp",
        "keywords": ["python", "automation", "testing"],
        "link": "https://example.com/job3"
    }
]

def match_jobs(skills_text):
    skills = [s.lower() for s in skills_text.split()]
    matched = []

    for job in JOBS:
        score = sum(1 for k in job["keywords"] if k in skills)
        if score > 0:
            matched.append((score, job))

    matched.sort(reverse=True, key=lambda x: x[0])
    return matched

import hashlib

def get_job_id(job):
    raw = f"{job['company']}|{job['title']}|{job['link']}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ==========================
# MAIN APP
# ==========================
def main():

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    job_queue = app.job_queue

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skills", set_skills))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("hrmsg", hrmsg))
    app.add_handler(CommandHandler("jobs", jobs))
    app.add_handler(CommandHandler("applied", applied))
    app.add_handler(CommandHandler("followups", followups))
    app.add_handler(CommandHandler("followupmsg", followupmsg))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("update_skill", update_skill))

    app.job_queue.run_daily(daily_jobs, time=time(hour=9))
    app.job_queue.run_daily(daily_followup, time=time(hour=9))
    app.job_queue.run_daily(weekly_summary,time=time(hour=10),days=(6,)   # Sunday
)


    print("🤖 Job Seeker Bot (PROD) running")
    app.run_polling(stop_signals=None)

if __name__ == "__main__":
    main()
