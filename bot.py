"""
Telegram Crypto Payment Bot
Currently exposed: USDT TRC-20 and SOL
Stores subscription price in GBP, converts GBP → crypto, and notifies admins.
"""

import logging
from datetime import datetime, timedelta, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, ChatJoinRequestHandler
)
from config import Config
from payment_manager import PaymentManager
from db import Database

CONFIRMING = 0

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

db = Database()
pm = PaymentManager()


def _format_dt(value) -> str:
    if not value:
        return "Unknown"

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M UTC")

    return str(value)


def _user_identity(update: Update) -> tuple[str, str]:
    telegram_username = update.effective_user.username
    display_name = update.effective_user.full_name or update.effective_user.first_name or "Unknown"

    username_line = (
        f"Username: @{telegram_username}\n"
        if telegram_username
        else "Username: no @username set\n"
    )

    return display_name, username_line


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
    for admin_id in Config.ADMIN_TELEGRAM_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception as e:
            logger.exception(f"Failed to notify admin {admin_id}: {e}")


# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username or user.first_name)

    keyboard = [
        [InlineKeyboardButton("💳 Pay Subscription", callback_data="create_invoice")],
        [InlineKeyboardButton("📋 My Invoices", callback_data="my_invoices")],
        [InlineKeyboardButton("💰 Wallet Addresses", callback_data="show_wallets")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]

    await update.message.reply_text(
        f"👋 Welcome, *{user.first_name}*!\n\n"
        "This bot helps you pay for private Telegram group access using crypto.\n\n"
        "Supported payment methods:\n"
        "💵 USDT TRC-20 · ◎ SOL\n\n"
        "Choose an option below:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── /help ────────────────────────────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 Bot Commands\n\n"
        "/start – Open the main menu\n"
        "/invoice – Create a new subscription invoice\n"
        "/invoices – View your recent invoices\n"
        "/wallets – View supported wallet addresses\n"
        "/help – Show this help message\n\n"
        "💡 How It Works\n"
        f"1. The subscription price is £{Config.MEMBERSHIP_PRICE_GBP:.2f} GBP\n"
        "2. Choose USDT TRC-20 or SOL\n"
        "3. The bot adds a small unique verification amount\n"
        "4. Send the exact crypto amount shown\n"
        "5. The bot automatically checks the blockchain\n"
        "6. After payment is confirmed, admins are notified to add you to the group\n\n"
        "🔐 Notes\n"
        "• Send only on the exact network shown\n"
        "• USDT TRC-20 is not the same as USDT ERC-20\n"
        "• Payments are subscriptions and expire after the configured period\n"
        "• Trading carries risk. Signals are not guaranteed outcomes."
    )

    if update.message:
        await update.message.reply_text(text)
    else:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]])
        )


# ─── Create Invoice Flow ──────────────────────────────────────────────────────
async def create_invoice_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["amount_gbp"] = Config.MEMBERSHIP_PRICE_GBP
    context.user_data["description"] = "Telegram group subscription"

    keyboard = [
        [InlineKeyboardButton("💵 USDT (TRC-20)", callback_data="coin_USDT_TRC20")],
        [InlineKeyboardButton("◎ SOL", callback_data="coin_SOL")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main_menu")],
    ]

    text = (
        "💳 *Group Subscription Payment*\n\n"
        f"Base price: *£{Config.MEMBERSHIP_PRICE_GBP:.2f} GBP*\n"
        f"Duration: *{Config.SUBSCRIPTION_DAYS} days*\n\n"
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


async def confirm_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    coin_key = query.data.replace("coin_", "")
    base_amount_gbp = context.user_data["amount_gbp"]

    amount_gbp, unique_adjustment_gbp = pm.generate_unique_gbp_amount(
        base_amount_gbp,
        coin_key,
        db
    )

    description = context.user_data["description"]
    user_id = update.effective_user.id

    wallet = pm.get_wallet(coin_key)
    crypto_amount = await pm.convert_gbp_to_crypto(amount_gbp, coin_key)

    invoice_id = db.create_invoice(
        user_id=user_id,
        coin=coin_key,
        amount_gbp=amount_gbp,
        unique_adjustment_gbp=unique_adjustment_gbp,
        crypto_amount=crypto_amount,
        wallet_address=wallet,
        description=description,
    )

    coin_labels = {
        "USDT_TRC20": "💵 USDT (TRC-20)",
        "SOL": "◎ Solana",
    }

    network_note = {
        "USDT_TRC20": "\n🔗 Network: TRON (TRC-20)",
        "SOL": "\n🔗 Network: Solana",
    }.get(coin_key, "")

    keyboard = [
        [InlineKeyboardButton("✅ Mark as Paid", callback_data=f"markpaid_{invoice_id}")],
        [InlineKeyboardButton("📋 My Invoices", callback_data="my_invoices")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")],
    ]

    await query.edit_message_text(
        f"🧾 *Invoice #{invoice_id} Created!*\n\n"
        f"📝 {description}\n"
        f"💷 Base Price: *£{base_amount_gbp:.2f} GBP*\n"
        f"🔐 Unique Verification Amount: *+£{unique_adjustment_gbp:.2f}*\n"
        f"💷 Total to Pay: *£{amount_gbp:.2f} GBP*\n"
        f"🪙 Crypto: *{coin_labels.get(coin_key, coin_key)}*{network_note}\n"
        f"💸 Exact Crypto Amount: *{crypto_amount}*\n\n"
        f"📬 Send to this address:\n"
        f"`{wallet}`\n\n"
        "⚠️ Send the exact crypto amount shown above on the correct network.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ConversationHandler.END


# ─── View Invoices ────────────────────────────────────────────────────────────
async def my_invoices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    invoices = db.get_user_invoices(user_id, limit=10)

    if not invoices:
        text = "📋 My Invoices\n\nYou have no invoices yet. Create one with /invoice"
    else:
        text = "📋 My Invoices (last 10)\n\n"
        status_icon = {"pending": "⏳", "paid": "✅", "expired": "❌"}

        for inv in invoices:
            icon = status_icon.get(inv["status"], "❓")
            amount_gbp = inv.get("amount_gbp") or inv.get("amount_usd") or 0

            text += (
                f"{icon} #{inv['id']} · £{float(amount_gbp):.2f} GBP · {inv['coin']}\n"
                f"   {inv['description'][:40] if inv.get('description') else ''}\n\n"
            )

    if query:
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]])
        )
    else:
        await update.message.reply_text(text)


# ─── Show Wallets ─────────────────────────────────────────────────────────────
async def show_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    wallets = {
        "💵 USDT TRC-20 (TRON)": Config.USDT_TRC20_WALLET,
        "◎ Solana (SOL)": Config.SOL_WALLET,
    }

    text = "💰 Supported Deposit Addresses\n\n"
    for label, addr in wallets.items():
        text += f"{label}\n{addr}\n\n"

    if query:
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]])
        )
    else:
        await update.message.reply_text(text)


# ─── Manual Mark as Paid ──────────────────────────────────────────────────────
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

    active_until = db.activate_subscription(
        user_id=user_id,
        days=Config.SUBSCRIPTION_DAYS
    )

    await query.edit_message_text(
        f"✅ Invoice #{invoice_id} Marked as Paid!\n\n"
        "Your payment has been flagged for manual admin review.\n"
        "An admin has been notified."
    )

    display_name, username_line = _user_identity(update)
    amount_gbp = invoice.get("amount_gbp") or invoice.get("amount_usd") or 0

    await notify_admins(
        context,
        (
            "⚠️ Manual Payment Marked as Paid\n\n"
            f"Invoice: #{invoice_id}\n"
            f"User ID: {user_id}\n"
            f"Name: {display_name}\n"
            f"{username_line}"
            f"Amount: £{float(amount_gbp):.2f} GBP\n"
            f"Coin: {invoice['coin']}\n"
            f"Subscription active until: {_format_dt(active_until)}\n\n"
            "Action: Manually verify payment, then add the user to the Telegram group."
        )
    )


# ─── Main Menu callback ───────────────────────────────────────────────────────
async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("💳 Pay Subscription", callback_data="create_invoice")],
        [InlineKeyboardButton("📋 My Invoices", callback_data="my_invoices")],
        [InlineKeyboardButton("💰 Wallet Addresses", callback_data="show_wallets")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]

    await query.edit_message_text(
        "🏠 Main Menu\n\nChoose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled. Use /start to begin again.")
    return ConversationHandler.END


# Kept for future use if the bot is made admin later.
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
            f"{invite.invite_link}"
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

            active_until = db.activate_subscription(
                user_id=invoice["user_id"],
                days=Config.SUBSCRIPTION_DAYS
            )

            amount_gbp = invoice.get("amount_gbp") or invoice.get("amount_usd") or 0
            user = db.get_user(invoice["user_id"])
            display_name = user["username"] if user and user.get("username") else "Unknown"

            await notify_admins(
                context,
                (
                    "✅ Blockchain Payment Verified\n\n"
                    f"Invoice: #{invoice['id']}\n"
                    f"User ID: {invoice['user_id']}\n"
                    f"Stored name/username: {display_name}\n"
                    f"Amount: £{float(amount_gbp):.2f} GBP\n"
                    f"Coin: {invoice['coin']}\n"
                    f"Transaction: {tx_hash}\n"
                    f"Subscription active until: {_format_dt(active_until)}\n\n"
                    "Action: Add the user to the Telegram group."
                )
            )

            try:
                await context.bot.send_message(
                    chat_id=invoice["user_id"],
                    text=(
                        "✅ Payment verified!\n\n"
                        f"Your subscription is active until {_format_dt(active_until)}. "
                        "An admin has been notified to add you to the group."
                    )
                )
            except Exception as e:
                logger.exception(f"Could not notify user {invoice['user_id']}: {e}")

            logger.info(f"Invoice {invoice['id']} paid via tx {tx_hash}")

        except Exception as e:
            logger.exception(f"Payment check failed for invoice {invoice['id']}: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────
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

    if app.job_queue:
        app.job_queue.run_repeating(
            check_pending_payments,
            interval=60,
            first=15
        )
    else:
        logger.warning("No JobQueue available. Install python-telegram-bot[job-queue].")

    print("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
