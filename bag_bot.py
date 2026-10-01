import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ==================== HEALTH SERVER ====================
flask_app = Flask(__name__)

@flask_app.route("/")
@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)

# ==================== TOKEN CONFIGURATION ====================
TOKEN_CONFIG = {
    "RPR": {
        "issuer": "r3qWgpz2ry3BhcRJ8JE6rxM8esrfhuKp4R",
        "fallback": 0.001991,
        "holding": 100000
    },
    "ASC": {
        "issuer": "r3qWgpz2ry3BhcRJ8JE6rxM8esrfhuKp4R",
        "fallback": 0.000426,
        "holding": 100000
    },
    "PLR": {
        "issuer": "rNSYhWLhuHvmURwWbJPBKZMSPsyG5Qek17",
        "fallback": 0.000715,
        "holding": 100000
    },
    "BOX": {
        "issuer": "rhy4FUHtXrMZhbkBfeYvDv4nz6R7M4cu1t",
        "fallback": 0.001078,
        "holding": 100000
    },
    "STX": {
        "issuer": "rSTAYKxF2K77ZLZ8GoAwTqPGaphAqMyXV",
        "fallback": 0.000003,
        "holding": 100000
    },
    "GRIM": {
        "issuer": "rHLRdLwXiBZSD53ZQz8ogGJz25LzNCCjSz",
        "fallback": 0.004164,
        "holding": 100000
    },
}

TOKEN_ORDER = ["RPR", "ASC", "PLR", "BOX", "STX", "GRIM"]

# ==================== LIVE DATA ====================
def get_live_xrp_usd():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ripple", "vs_currencies": "usd"},
            timeout=8
        )
        return float(r.json()["ripple"]["usd"])
    except Exception:
        return None

def get_live_token_prices_in_xrp():
    live = {t: None for t in TOKEN_ORDER}
    headers = {"User-Agent": "CapitalRevivalBot/2.6"}

    # Query Dexscreener by token symbol and validate issuer/chain to prevent shared-issuer overlap
    for token in TOKEN_ORDER:
        issuer = TOKEN_CONFIG[token]["issuer"]
        try:
            r = requests.get(
                f"https://api.dexscreener.com/latest/dex/search?q={token}",
                headers=headers,
                timeout=6
            )
            if r.status_code == 200:
                pairs = r.json().get("pairs", [])
                for p in pairs:
                    if p.get("chainId") != "xrpl":
                        continue
                    base = p.get("baseToken", {})
                    quote = p.get("quoteToken", {})
                    
                    base_symbol = base.get("symbol", "").upper()
                    base_addr = base.get("address", "")
                    
                    if base_symbol == token and quote.get("symbol", "").upper() == "XRP":
                        if issuer.lower() in base_addr.lower() or token in ["ASC", "RPR"]:
                            price_native = p.get("priceNative")
                            if price_native is not None:
                                live[token] = float(price_native)
                                break
        except Exception:
            pass

    return live

# ==================== COMMANDS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📊 *Capital Revival Calculator*\n\n"
        "Estimates what RPR, ASC, PLR, BOX, STX & GRIM could be worth at different XRP prices.\n\n"
        "*How to use:*\n\n"
        "• Type an XRP price\n"
        "  Example: `1.50`\n\n"
        "• Custom bag\n"
        "  Example: `50000 rpr 1.50`\n\n"
        "• Custom ratio + XRP price\n"
        "  Example: `100000 rpr @ 0.40 589`\n\n"
        "Type /help for more commands\n"
        "Type /info to understand live vs estimated prices"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛠 *Commands*\n\n"
        "/start – Welcome message\n"
        "/help – This help message\n"
        "/info – How the calculator works\n"
        "/calc – Use current live XRP price\n\n"
        "*How to calculate:*\n\n"
        "• Just an XRP price: `1.50`\n"
        "• Custom bag + XRP price: `50000 rpr 1.50`\n"
        "• Custom ratio + XRP price: `100000 rpr @ 0.40 589`\n\n"
        "🟢 = Live market price\n"
        "⚪ = Estimated ratio"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *How this calculator works*\n\n"
        "This bot estimates token values based on an XRP price using official XRPL issuer addresses.\n\n"
        "*Two types of data:*\n\n"
        "🟢 *Live prices*\n"
        "Pulled in real time from Dexscreener via verified issuer contracts.\n\n"
        "⚪ *Estimated ratios*\n"
        "Used only when live data cannot be fetched.\n\n"
        "Data sources: CoinGecko (XRP), Dexscreener (XRPL)"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ==================== MAIN CALCULATOR ====================
async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lower()
    parts = raw.replace("@", " @ ").split()

    if parts and parts[0] in ["/calc", "/bag", "/live", "/price", "/start", "/help", "/info"]:
        parts = parts[1:]

    live_xrp = get_live_xrp_usd()
    live_tokens = get_live_token_prices_in_xrp()

    # ---------- Custom bag detection ----------
    detected_token = None
    for p in parts:
        if p.upper() in TOKEN_CONFIG:
            detected_token = p.upper()
            break

    if detected_token:
        numbers = []
        for p in parts:
            if p.upper() == detected_token or p == "@":
                continue
            try:
                numbers.append(float(p.replace("$", "").replace(",", "")))
            except ValueError:
                pass

        if len(numbers) >= 2:
            amount = numbers[0]
            
            # If 3 numbers are provided: [amount, custom_ratio, xrp_price]
            if len(numbers) >= 3:
                ratio = numbers[1]
                xrp_price = numbers[2]
                source = "Custom Ratio"
            else:
                # If 2 numbers are provided: [amount, xrp_price] (uses live/fallback ratio)
                ratio = live_tokens.get(detected_token) or TOKEN_CONFIG[detected_token]["fallback"]
                xrp_price = numbers[1]
                source = "Live" if live_tokens.get(detected_token) is not None else "Estimated"

            if xrp_price <= 0 and live_xrp:
                xrp_price = live_xrp

            total = amount * ratio * xrp_price

            reply = (
                f"🎯 *Custom Bag*\n\n"
                f"• Holding: `{amount:,.0f} {detected_token}`\n"
                f"• Ratio: `{ratio:.6f} XRP` ({source})\n"
                f"• XRP Price: `${xrp_price:,.4f}`\n\n"
                f"💰 *Total Value: ${total:,.2f}*"
            )
            await update.message.reply_text(reply, parse_mode="Markdown")
            return

    # ---------- Normal portfolio view ----------
    xrp_price = None
    if len(parts) == 1:
        try:
            xrp_price = float(parts[0].replace("$", "").replace(",", ""))
        except ValueError:
            pass

    if xrp_price is None or xrp_price <= 0:
        if live_xrp is None:
            await update.message.reply_text(
                "Could not fetch live XRP price right now.\nPlease type a number (example: `1.50`)."
            )
            return
        xrp_price = live_xrp
        mode = "Current Live XRP"
    else:
        mode = "Your Target XRP Price"

    lines = [f"📈 *XRP Price: ${xrp_price:,.4f}* ({mode})\n"]
    lines.append("💼 *Example Portfolio (100,000 of each):*\n")

    total = 0.0
    for token in TOKEN_ORDER:
        ratio = live_tokens.get(token) or TOKEN_CONFIG[token]["fallback"]
        is_live = live_tokens.get(token) is not None
        value = ratio * xrp_price * TOKEN_CONFIG[token]["holding"]
        total += value
        tag = "🟢" if is_live else "⚪"
        lines.append(f"{tag} *{token}*: `${value:,.2f}`   ({ratio:.6f} XRP)")

    lines.append(f"\n🚀 *Total: ${total:,.2f}*")
    lines.append(
        "\n🟢 = Live market price\n"
        "⚪ = Estimated ratio\n\n"
        "Try a custom bag: `50000 rpr 1.50`"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ==================== MAIN ====================
def main():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("Please set the TELEGRAM_BOT_TOKEN environment variable")

    # Start Flask health check server in background thread for Railway
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start Telegram Bot
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler(["calc", "bag", "live", "price"], calc))

    text_filter = filters.TEXT & ~filters.COMMAND
    app.add_handler(MessageHandler(text_filter, calc))

    print("Capital Revival Calculator is running on Railway...")
    app.run_polling()

if __name__ == "__main__":
    main()
