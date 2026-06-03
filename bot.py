"""
Telegram Crypto Payment Bot
Supports: BTC, ETH, USDT (ERC-20 & TRC-20), SOL, LTC, TRX
"""

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
    ChatJoinRequestHandler
)
from config import Config
from payment_manager import PaymentManager
from db import Database
from datetime import datetime, timedelta, timezone

# States
AWAITING_AMOUNT, AWAITING_DESCRIPTION, CONFIRMING = range(3)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

db = Database()
pm = PaymentManager()


# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or user.first_name)

    keyboard = [
        [InlineKeyboardButton("💳 Create Invoice", callback_data="create_invoice")],
        [InlineKeyboardButton("📋 My Invoices", callback_data="my_invoices")],
        [InlineKeyboardButton("💰 Wallet Addresses", callback_data="show_wallets")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    await update.message.reply_text(
        f"👋 Welcome, *{user.first_name}*!\n\n"
        "I'm your *Crypto Payment Bot*. Accept payments in:\n"
        "₿ BTC · Ξ ETH · 💵 USDT · ◎ SOL · Ł LTC · ⚡ TRX\n\n"
        "Choose an option below to get started:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── /help ────────────────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Bot Commands\n\n"
        "/start – Open the main menu\n"
        "/invoice – Create a new crypto invoice\n"
        "/invoices – View your recent invoices\n"
        "/wallets – View supported wallet addresses\n"
        "/help – Show this help message\n\n"
        "💡 How It Works\n"
        "1. Create an invoice in USD\n"
        "2. Choose a cryptocurrency\n"
        "3. The bot generates a unique payment amount\n"
        "4. Send the exact amount shown\n"
        "5. The bot automatically verifies the blockchain payment\n"
        "6. Once verified, you'll receive a private Telegram group access link\n\n"
        "🔐 Security Features\n"
        "• Unique payment amounts prevent payment mix-ups\n"
        "• Blockchain payments are verified automatically\n"
        "• Group access links expire automatically\n"
        "• Join requests are approved only for verified users\n\n"
        "⏱️ Most payments are detected within 1–2 minutes depending on blockchain confirmations."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]]))


# ─── Create Invoice Flow ───────────────────────────────────────────────────────
async def create_invoice_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["amount"] = 0.01
    context.user_data["description"] = "Telegram group access"

    keyboard = [
        [InlineKeyboardButton("💵 USDT (TRC-20)", callback_data="coin_USDT_TRC20")],
        [InlineKeyboardButton("◎ SOL", callback_data="coin_SOL")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")],
    ]

    text = (
        "💳 *Group Access Payment*\n\n"
        "Amount: *$0.01 USD*\n\n"
        "Choose your payment method:"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    return CONFIRMING


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace("$", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a positive number:")
        return AWAITING_AMOUNT

    context.user_data["amount"] = amount
    await update.message.reply_text(
        f"✅ Amount: *${amount:.2f} USD*\n\n"
        "Now enter a *description* for this invoice:\n"
        "_Example: Website design service_",
        parse_mode="Markdown"
    )
    return AWAITING_DESCRIPTION


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text.strip()[:200]
    amount = context.user_data["amount"]
    desc = context.user_data["description"]

    keyboard = [
        [
            InlineKeyboardButton("₿ BTC", callback_data="coin_BTC"),
            InlineKeyboardButton("Ξ ETH", callback_data="coin_ETH"),
        ],
        [
            InlineKeyboardButton("💵 USDT (ERC-20)", callback_data="coin_USDT_ERC20"),
            InlineKeyboardButton("💵 USDT (TRC-20)", callback_data="coin_USDT_TRC20"),
        ],
        [
            InlineKeyboardButton("◎ SOL", callback_data="coin_SOL"),
            InlineKeyboardButton("Ł LTC", callback_data="coin_LTC"),
        ],
        [
            InlineKeyboardButton("⚡ TRX", callback_data="coin_TRX"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")],
    ]

    await update.message.reply_text(
        f"📋 *Invoice Preview*\n\n"
        f"💵 Amount: *${amount:.2f} USD*\n"
        f"📝 Description: _{desc}_\n\n"
        "Select the *cryptocurrency* for payment:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRMING


async def confirm_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    coin_key = query.data.replace("coin_", "")
    # base_amount_usd = context.user_data["amount"]
    # amount_usd, unique_adjustment = pm.generate_unique_usd_amount(
    #     base_amount_usd,
    #     coin_key,
    #     db
    #     )
    base_amount_usd = context.user_data["amount"]
    amount_usd = base_amount_usd
    unique_adjustment = 0.00
    description = context.user_data["description"]
    user_id = update.effective_user.id

    # Get wallet address and convert amount
    wallet = pm.get_wallet(coin_key)
    crypto_amount = await pm.convert_usd_to_crypto(amount_usd, coin_key)

    # Save invoice to DB
    invoice_id = db.create_invoice(
        user_id=user_id,
        coin=coin_key,
        amount_usd=amount_usd,
        crypto_amount=crypto_amount,
        wallet_address=wallet,
        description=description,
    )

    coin_labels = {
        "BTC": "₿ Bitcoin", "ETH": "Ξ Ethereum",
        "USDT_ERC20": "💵 USDT (ERC-20)", "USDT_TRC20": "💵 USDT (TRC-20)",
        "SOL": "◎ Solana", "LTC": "Ł Litecoin", "TRX": "⚡ TRON"
    }
    network_note = {
        "USDT_ERC20": "\n🔗 _Network: Ethereum (ERC-20)_",
        "USDT_TRC20": "\n🔗 _Network: TRON (TRC-20)_",
    }.get(coin_key, "")

    keyboard = [
        [InlineKeyboardButton("✅ Mark as Paid", callback_data=f"markpaid_{invoice_id}")],
        [InlineKeyboardButton("📋 My Invoices", callback_data="my_invoices")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ]

    await query.edit_message_text(
        f"🧾 *Invoice #{invoice_id} Created!*\n\n"
        f"📝 _{description}_\n"
        f"💵 USD Amount: *${amount_usd:.2f}*\n"
        f"🪙 Crypto: *{coin_labels[coin_key]}*{network_note}\n"
        f"💵 Base Amount: *${base_amount_usd:.2f}*\n"
        f"🔐 Unique Verification Amount: *+${unique_adjustment:.2f}*\n"
        f"💵 Total to Pay: *${amount_usd:.2f}*\n"
        f"📬 *Send to this address:*\n"
        f"`{wallet}`\n\n"
        f"⚠️ _Send the exact amount shown above. This unique amount helps verify your payment automatically._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# ─── View Invoices ─────────────────────────────────────────────────────────────
async def my_invoices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    invoices = db.get_user_invoices(user_id, limit=10)

    if not invoices:
        text = "📋 *My Invoices*\n\nYou have no invoices yet. Create one with /invoice"
    else:
        text = "📋 *My Invoices* (last 10)\n\n"
        status_icon = {"pending": "⏳", "paid": "✅", "expired": "❌"}
        for inv in invoices:
            icon = status_icon.get(inv["status"], "❓")
            text += (
                f"{icon} *#{inv['id']}* · ${inv['amount_usd']:.2f} · {inv['coin']}\n"
                f"   _{inv['description'][:40]}_\n\n"
            )

    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]]))
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


# ─── Show Wallets ──────────────────────────────────────────────────────────────
async def show_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    wallets = pm.get_all_wallets()
    text = "💰 *Your Deposit Addresses*\n\n"
    for label, addr in wallets.items():
        text += f"*{label}*\n`{addr}`\n\n"

    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]]))
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def mark_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    invoice_id = int(query.data.split("_")[1])
    user_id = update.effective_user.id
    invoice = db.get_invoice(invoice_id)

    if not invoice or invoice["user_id"] != user_id:
        await query.edit_message_text("❌ Invoice not found.")
        return

    db.update_invoice_status(invoice_id, "paid", tx_hash=f"manual_test_{invoice_id}")

    await query.edit_message_text(
        f"✅ *Invoice #{invoice_id} Marked as Paid!*\n\n"
        "Your payment has been flagged for manual review.\n"
        "An admin has been notified.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])
    )

    telegram_username = update.effective_user.username
    display_name = update.effective_user.full_name or update.effective_user.first_name or "Unknown"

    username_line = (
        f"Username: @{telegram_username}\n"
        if telegram_username
        else "Username: no @username set\n"
    )

    if Config.ADMIN_TELEGRAM_ID:
        await context.bot.send_message(
            chat_id=Config.ADMIN_TELEGRAM_ID,
            text=(
                "⚠️ Manual Payment Marked as Paid\n\n"
                f"Invoice: #{invoice_id}\n"
                f"User ID: {user_id}\n"
                f"Name: {display_name}\n"
                f"{username_line}"
                f"Amount: ${invoice['amount_usd']:.2f}\n"
                f"Coin: {invoice['coin']}\n\n"
                "Please verify the payment manually and send the user the group link."
            )
        )


# ─── Main Menu callback ────────────────────────────────────────────────────────
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💳 Create Invoice", callback_data="create_invoice")],
        [InlineKeyboardButton("📋 My Invoices", callback_data="my_invoices")],
        [InlineKeyboardButton("💰 Wallet Addresses", callback_data="show_wallets")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    await query.edit_message_text(
        "🏠 *Main Menu*\n\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Use /start to begin again.")
    return ConversationHandler.END


async def send_group_invite(context: ContextTypes.DEFAULT_TYPE, user_id: int, invoice_id: int):
    invite = await context.bot.create_chat_invite_link(
        chat_id=Config.GROUP_ID,
        name=f"invoice_{invoice_id}_user_{user_id}",
        expire_date=datetime.now(timezone.utc) + timedelta(hours=1),
        member_limit=1,
        creates_join_request=True
    )

    db.mark_invite_sent(invoice_id, invite.invite_link)

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "✅ Payment verified!\n\n"
            "Here is your private group access link:\n"
            f"{invite.invite_link}\n\n"
            "It expires in 1 hour."
        )
    )


async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    user_id = request.from_user.id

    if db.user_has_paid_invoice(user_id):
        await context.bot.approve_chat_join_request(
            chat_id=request.chat.id,
            user_id=user_id
        )
    else:
        await context.bot.decline_chat_join_request(
            chat_id=request.chat.id,
            user_id=user_id
        )


async def check_pending_payments(context: ContextTypes.DEFAULT_TYPE):
    pending = db.get_pending_invoices(limit=25)

    for invoice in pending:
        try:
            is_paid, tx_hash = await pm.verify_invoice(invoice, db)

            if not is_paid:
                continue

            db.update_invoice_status(invoice["id"], "paid", tx_hash=tx_hash)

            await send_group_invite(
                context=context,
                user_id=invoice["user_id"],
                invoice_id=invoice["id"]
            )

            logger.info(f"Invoice {invoice['id']} paid via tx {tx_hash}")

        except Exception as e:
            logger.exception(f"Payment check failed for invoice {invoice['id']}: {e}")


# ─── Main ──────────────────────────────────────────────────────────────────────
def main():
    token = Config.TELEGRAM_TOKEN
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("❌ Please set TELEGRAM_BOT_TOKEN in your .env file")
        return

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(create_invoice_start, pattern="^create_invoice$"),
            CommandHandler("invoice", create_invoice_start),
        ],
        states={
            AWAITING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            AWAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)],
            CONFIRMING: [CallbackQueryHandler(confirm_coin, pattern="^coin_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"),
        ],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("wallets", show_wallets))
    app.add_handler(CommandHandler("invoices", my_invoices))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(my_invoices, pattern="^my_invoices$"))
    app.add_handler(CallbackQueryHandler(show_wallets, pattern="^show_wallets$"))
    app.add_handler(CallbackQueryHandler(help_command, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(mark_paid, pattern="^markpaid_"))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))

    app.job_queue.run_repeating(
        check_pending_payments,
        interval=60,
        first=15
        )
    print("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)

    
if __name__ == "__main__":
    main()