from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes

)
import os
from datetime import datetime, timedelta
import sqlite3

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

# ==========================
# CONFIG
# ==========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# In-memory storage (simple, free)
user_skills = {}

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

    skills_text = " ".join(context.args)
    user_skills[update.effective_user.id] = skills_text

    await update.message.reply_text(
        f"✅ Skills saved:\n{skills_text}"
    )

async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    skills = user_skills.get(update.effective_user.id, "your skills")

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
    skills = user_skills.get(update.effective_user.id)

    if not skills:
        await update.message.reply_text("❌ Set skills first using /skills")
        return

    matches = match_jobs(skills)

    if not matches:
        await update.message.reply_text("❌ No matching jobs today")
        return

    msg = "🔥 Matching jobs for you today:\n\n"
    for score, job in matches:
        msg += (
            f"✅ {job['title']} ({job['company']})\n"
            f"🔗 {job['link']}\n\n"
        )

    await update.message.reply_text(msg)

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
        (user_id, company, role, datetime.utcnow().isoformat())
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

    now = datetime.utcnow()
    msg = "🔔 FOLLOW-UP REMINDERS:\n\n"
    due = False

    for company, role, applied_at in rows:
        applied_time = datetime.fromisoformat(applied_at)
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

        # TEMP: 1 minute for testing (change to days=5 later)
        if datetime.utcnow() - applied_time >= timedelta(days=5):
            reminders.setdefault(user_id, []).append(
                f"📌 Follow up: {company} – {role}"
            )

    for user_id, msgs in reminders.items():
        await context.bot.send_message(
            chat_id=user_id,
            text="🔔 Follow-up Reminder\n\n" + "\n".join(msgs)
        )

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
    
    job_queue.run_daily(daily_followup, time=datetime.time(hour=9))
    # job_queue.run_repeating(daily_followup, interval=60, first=10)




    print("🤖 Job Seeker Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
