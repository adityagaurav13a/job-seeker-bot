from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

# ==========================
# CONFIG
# ==========================
BOT_TOKEN = "7959091314:AAGpcBspfAs8vLVbdm7A5KNgYSiAjjIjRTg"

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

# ==========================
# MAIN APP
# ==========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("skills", set_skills))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(CommandHandler("hrmsg", hrmsg))

    print("🤖 Job Seeker Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
