import os
import json
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DATA_FILE = "gtd_data.json"

# Gemini setup
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# GTD data structure
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"inbox": [], "next_actions": [], "projects": [], "someday": [], "done": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def classify_with_ai(text):
    prompt = f"""Sen GTD (Getting Things Done) yordamchisisан. Foydalanuvchi quyidagi matnni yubordi:

"{text}"

Ushbu matnni tahlil qilib, quyidagi JSON formatida qaytар (faqat JSON, boshqa narsa yozma):
{{
  "category": "next_action | project | someday | inbox",
  "title": "qisqa sarlavha (o'zbek tilida)",
  "action": "eng birinchi bajariladigan harakat (next_action yoki project uchun)",
  "notes": "qo'shimcha izoh (agar kerak bo'lsa)",
  "why": "nima uchun bu kategoriyani tanladingiz (1 jumla)"
}}

Kategoriyalar:
- next_action: hozir yoki tez orada bajarilishi mumkin bo'lgan bitta aniq harakat
- project: 2+ qadam talab qiladigan maqsad
- someday: kelajakda qilish mumkin, lekin hozir emas
- inbox: noaniq, keyinroq qayta ko'rib chiqish kerak"""

    response = model.generate_content(prompt)
    text_response = response.text.strip()
    # Clean up markdown if present
    if "```json" in text_response:
        text_response = text_response.split("```json")[1].split("```")[0].strip()
    elif "```" in text_response:
        text_response = text_response.split("```")[1].split("```")[0].strip()
    return json.loads(text_response)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧠 *GTD Botingizga xush kelibsiz!*\n\n"
        "Miyangizni tozalang — har qanday fikr, vazifa, reja yozing.\n"
        "Men uni avtomatik tartibga solaman.\n\n"
        "📌 *Buyruqlar:*\n"
        "/inbox — Inbox ro'yxati\n"
        "/next — Next Actions\n"
        "/projects — Loyihalar\n"
        "/someday — Someday/Maybe\n"
        "/done — Bajarilganlar\n"
        "/review — Haftalik review\n"
        "/clear\\_inbox — Inboxni tozalash\n\n"
        "Yoki shunchaki xabar yozing! ✍️",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    data = load_data()

    await update.message.reply_text("🔄 Tahlil qilinmoqda...")

    try:
        result = classify_with_ai(user_text)
        category = result.get("category", "inbox")
        title = result.get("title", user_text[:50])
        action = result.get("action", "")
        notes = result.get("notes", "")
        why = result.get("why", "")

        item = {
            "id": len(data[category]) + 1,
            "title": title,
            "original": user_text,
            "action": action,
            "notes": notes,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "done": False
        }

        data[category].append(item)
        save_data(data)

        category_emojis = {
            "next_action": "⚡ Next Action",
            "project": "📁 Loyiha",
            "someday": "🌙 Someday/Maybe",
            "inbox": "📥 Inbox"
        }

        response = f"✅ *Saqlandi: {category_emojis.get(category, '📥 Inbox')}*\n\n"
        response += f"📌 *{title}*\n"
        if action:
            response += f"▶️ Birinchi qadam: {action}\n"
        if notes:
            response += f"📝 Izoh: {notes}\n"
        response += f"\n💡 _{why}_"

        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error: {e}")
        # Fallback to inbox
        data["inbox"].append({
            "id": len(data["inbox"]) + 1,
            "title": user_text[:100],
            "original": user_text,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "done": False
        })
        save_data(data)
        await update.message.reply_text("📥 Inboxga saqlandi. Keyinroq qayta ko'rib chiqing.")

async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str, title: str, emoji: str):
    data = load_data()
    items = [i for i in data[category] if not i.get("done", False)]

    if not items:
        await update.message.reply_text(f"{emoji} *{title}* bo'sh.\n\nYangi narsa yozing!", parse_mode="Markdown")
        return

    text = f"{emoji} *{title}* ({len(items)} ta):\n\n"
    for i, item in enumerate(items, 1):
        text += f"{i}. {item['title']}\n"
        if item.get("action"):
            text += f"   ▶️ {item['action']}\n"
        text += f"   📅 {item.get('date', '')}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def inbox_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_list(update, context, "inbox", "Inbox", "📥")

async def next_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_list(update, context, "next_actions", "Next Actions", "⚡")

async def projects_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_list(update, context, "projects", "Loyihalar", "📁")

async def someday_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_list(update, context, "someday", "Someday/Maybe", "🌙")

async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    items = data.get("done", [])
    if not items:
        await update.message.reply_text("✅ Hali bajarilgan vazifalar yo'q.")
        return
    text = f"✅ *Bajarilganlar* (oxirgi {min(10, len(items))} ta):\n\n"
    for item in items[-10:]:
        text += f"✔️ {item['title']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def review_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    inbox_count = len([i for i in data["inbox"] if not i.get("done")])
    next_count = len([i for i in data["next_actions"] if not i.get("done")])
    project_count = len([i for i in data["projects"] if not i.get("done")])
    someday_count = len([i for i in data["someday"] if not i.get("done")])

    text = f"📊 *Haftalik Review*\n\n"
    text += f"📥 Inbox: {inbox_count} ta\n"
    text += f"⚡ Next Actions: {next_count} ta\n"
    text += f"📁 Loyihalar: {project_count} ta\n"
    text += f"🌙 Someday: {someday_count} ta\n\n"

    if inbox_count > 0:
        text += "⚠️ Inboxda vazifalar bor — qayta ko'rib chiqing!\n"
    if next_count == 0:
        text += "💡 Next Actions bo'sh — bugun nima qilasiz?\n"
    else:
        text += f"✅ Bugun {min(3, next_count)} ta vazifani bajaring!\n"

    await update.message.reply_text(text, parse_mode="Markdown")

async def clear_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📥 Inboxni tozalash uchun har bir vazifani qayta yozing va men uni to'g'ri joyga joylashaman.\n\n"
        "/inbox buyrug'i bilan ko'ring va qayta ishlamoqchi bo'lgan vazifani yozing."
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("inbox", inbox_cmd))
    app.add_handler(CommandHandler("next", next_cmd))
    app.add_handler(CommandHandler("projects", projects_cmd))
    app.add_handler(CommandHandler("someday", someday_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("review", review_cmd))
    app.add_handler(CommandHandler("clear_inbox", clear_inbox))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
