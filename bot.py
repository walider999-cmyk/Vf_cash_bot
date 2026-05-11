import os
import re
import json
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== إعدادات البوت =====
TOKEN = os.environ.get("BOT_TOKEN", "8772902857:AAFUMK37-eLsmeYzJs3kQ2jfsTLZgWQKiQw")
OWNER_CHAT_ID = int(os.environ.get("OWNER_CHAT_ID", "1105203699"))
COMMISSION_RATE = 0.01  # 1% عمولة السحب

# ===== تخزين البيانات =====
DATA_FILE = "transactions.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"transactions": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== استخراج المبلغ من رسالة فودافون كاش =====
def parse_vodafone_sms(text):
    """
    مثال الرسالة:
    تم استلام مبلغ 725 جنيه من رقم 01015726991
    """
    result = {"amount": None, "type": None, "ref": None, "balance": None}

    # استخراج المبلغ
    amount_match = re.search(r'مبلغ\s+([\d,]+(?:\.\d+)?)\s*جنيه', text)
    if amount_match:
        result["amount"] = float(amount_match.group(1).replace(",", ""))

    # تحديد نوع العملية
    if "تم استلام" in text or "استلام" in text:
        result["type"] = "deposit"  # إيداع على المحل
    elif "تم تحويل" in text or "تحويل" in text or "سحب" in text:
        result["type"] = "withdraw"  # سحب من المحل

    # استخراج رقم العملية
    ref_match = re.search(r'رقم العملية\s*\n?([\d]+)', text)
    if ref_match:
        result["ref"] = ref_match.group(1)

    # استخراج الرصيد
    balance_match = re.search(r'رصيدك الحالي\s+([\d,]+(?:\.\d+)?)', text)
    if balance_match:
        result["balance"] = float(balance_match.group(1).replace(",", ""))

    return result

# ===== حساب العمولة =====
def calc_commission(amount, tx_type):
    if tx_type == "withdraw":
        return amount * COMMISSION_RATE
    return 0  # الإيداع مجاني

# ===== أوامر البوت =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 أهلاً! أنا بوت تتبع عمليات فودافون كاش\n\n"
        "📤 ابعتلي نص رسالة SMS وأنا هسجلها تلقائياً\n\n"
        "الأوامر المتاحة:\n"
        "/today - تقرير اليوم\n"
        "/summary - ملخص شامل\n"
        "/clear - مسح عمليات اليوم"
    )

async def today_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_tx = [t for t in data["transactions"] if t["date"] == today]

    if not today_tx:
        await update.message.reply_text("📭 لا توجد عمليات مسجلة اليوم")
        return

    withdrawals = [t for t in today_tx if t["type"] == "withdraw"]
    deposits = [t for t in today_tx if t["type"] == "deposit"]

    total_withdraw = sum(t["amount"] for t in withdrawals)
    total_deposit = sum(t["amount"] for t in deposits)
    total_commission = sum(t["commission"] for t in today_tx)

    msg = f"📊 *تقرير يوم {today}*\n\n"
    msg += f"📤 *السحب:*\n"
    msg += f"  عدد العمليات: {len(withdrawals)}\n"
    msg += f"  إجمالي المبالغ: {total_withdraw:,.2f} ج\n"
    msg += f"  العمولة (1%): {sum(t['commission'] for t in withdrawals):,.2f} ج\n\n"
    msg += f"📥 *الإيداع:*\n"
    msg += f"  عدد العمليات: {len(deposits)}\n"
    msg += f"  إجمالي المبالغ: {total_deposit:,.2f} ج\n"
    msg += f"  العمولة: مجاني\n\n"
    msg += f"💰 *إجمالي العمولات: {total_commission:,.2f} ج*"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data["transactions"]:
        await update.message.reply_text("📭 لا توجد عمليات مسجلة")
        return

    total_commission = sum(t["commission"] for t in data["transactions"])
    total_withdraw = sum(t["amount"] for t in data["transactions"] if t["type"] == "withdraw")
    total_deposit = sum(t["amount"] for t in data["transactions"] if t["type"] == "deposit")
    count = len(data["transactions"])

    msg = f"📈 *الملخص الكامل*\n\n"
    msg += f"إجمالي العمليات: {count}\n"
    msg += f"إجمالي السحب: {total_withdraw:,.2f} ج\n"
    msg += f"إجمالي الإيداع: {total_deposit:,.2f} ج\n"
    msg += f"💰 *إجمالي العمولات: {total_commission:,.2f} ج*"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def clear_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != OWNER_CHAT_ID:
        await update.message.reply_text("❌ مش مسموح")
        return
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    data["transactions"] = [t for t in data["transactions"] if t["date"] != today]
    save_data(data)
    await update.message.reply_text("✅ تم مسح عمليات اليوم")

# ===== معالجة الرسايل =====
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parsed = parse_vodafone_sms(text)

    if not parsed["amount"]:
        await update.message.reply_text(
            "⚠️ مش قادر أقرأ المبلغ من الرسالة دي\n"
            "تأكد إن الرسالة من فودافون كاش وفيها كلمة 'مبلغ'"
        )
        return

    # تسجيل العملية
    data = load_data()
    tx = {
        "id": len(data["transactions"]) + 1,
        "type": parsed["type"] or "unknown",
        "amount": parsed["amount"],
        "commission": calc_commission(parsed["amount"], parsed["type"]),
        "ref": parsed["ref"] or "—",
        "balance": parsed["balance"],
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M:%S"),
        "raw": text[:100]
    }
    data["transactions"].append(tx)
    save_data(data)

    # رد التأكيد
    type_ar = "📤 سحب" if tx["type"] == "withdraw" else "📥 إيداع"
    commission_text = f"{tx['commission']:,.2f} ج" if tx['commission'] > 0 else "مجاني ✓"

    msg = f"✅ *تم التسجيل*\n\n"
    msg += f"النوع: {type_ar}\n"
    msg += f"المبلغ: *{tx['amount']:,.2f} ج*\n"
    msg += f"العمولة: *{commission_text}*\n"
    msg += f"رقم العملية: `{tx['ref']}`\n"
    msg += f"الوقت: {tx['time']}"

    if parsed["balance"]:
        msg += f"\nالرصيد المتبقي: {parsed['balance']:,.2f} ج"

    await update.message.reply_text(msg, parse_mode="Markdown")

    # إشعار لصاحب المحل
    if update.effective_chat.id != OWNER_CHAT_ID:
        bot = context.bot
        await bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"🔔 *عملية جديدة*\n{msg}",
            parse_mode="Markdown"
        )

# ===== تشغيل البوت =====
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today_report))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("clear", clear_today))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ البوت شغال!")
    app.run_polling()

if __name__ == "__main__":
    main()
