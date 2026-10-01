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
    flask_app.run(host="0.0.0.0", port=port)

# ==================== SETTINGS ====================
DEFAULT_HOLDINGS = {
    "RPR": 100000,
    "ASC": 100000,
    "PLR": 100000,
    "BOX": 100000,
    "STX": 100000,
    "GRIM": 100000,
}

FALLBACK_RATIOS = {
    "RPR": 0.0025,
    "ASC": 0.0006,
    "PLR": 0.0009,
    "BOX": 0.00015,
    "STX": 0.000004,
    "GRIM": 0.0042,
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
    headers = {"User-Agent": "CapitalRevivalBot/2.0"}

    # Source 1: Dexscreener
    for token in TOKEN_ORDER:
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
                    if base.get("symbol", "").upper() == token:
                        price_native = p.get("priceNative")
                        if price_native is not None:
                            live[token] = float(price_native)
                            break
        except Exception:
            pass

    # Source 2: XRPL.to
    try:
        r = requests.get("https://api.xrpl.to/v1/tokens?limit=250", headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            tokens = data.get("tokens", data) if isinstance(data, dict) else data
            if isinstance(tokens, list):
                for item in tokens:
                    symbol = str(
                        item.get("name") or item.get("currency") or
                        item.get("symbol") or item.get("code") or ""
                    ).upper()
                    price = (
                        item.get("exch") or item.get("price") or
                        item.get("price_xrp") or item.get("rate")
                    )
                    if symbol in live and live[symbol] is None and price is not None:
                        try:
                            live[symbol] = float(price)
                        except (ValueError, TypeError):
                            pass
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
        "• Advanced (custom ratio)\n"
        "  Example: `50000 rpr @ 0.0025 1.50`\n\n"
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
        "• Just an XRP price\n"
        "  `1.50`\n\n"
        "• Custom bag + XRP price\n"
        "  `50000 rpr 1.50`\n\n"
        "• Custom ratio\n"
        "  `50000 rpr @ 0.0025 1.50`\n\n"
        "🟢 = Live market price\n"
        "⚪ = Estimated ratio"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *How this calculator works*\n\n"
        "This bot estimates token values based on an XRP price.\n\n"
        "*Two types of data:*\n\n"
        "🟢 *Live prices*\n"
        "Pulled in real time from Dexscreener and XRPL.to when available.\n\n"
        "⚪ *Estimated ratios*\n"
        "Used only when live data cannot be fetched. These are approximate values.\n\n"
        "*Important notes:*\n"
        "• This is a projection tool, not financial advice\n"
        "• Live prices on the XRPL DEX can change quickly\n"
        "• The 100,000 size is only an example portfolio\n\n"
        "Data sources: CoinGecko (XRP), Dexscreener & XRPL.to"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ==================== MAIN CALCULATOR ====================
async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lower()
    parts = raw.replace("@", " @ ").split()

    # Remove command if present
    if parts and parts[0] in ["/calc", "/bag", "/live", "/price", "/start", "/help", "/info"]:
        parts = parts[1:]

    live_xrp = get_live_xrp_usd()
    live_tokens = get_live_token_prices_in_xrp()

    # ---------- Custom bag detection ----------
    detected_token = None
    for p in parts:
        if p.upper() in FALLBACK_RATIOS:
            detected_token = p.upper()
            break

    if detected_token:
        numbers = []
        for p in parts:
            if p.upper() == detected_token:
                continue
            try:
                numbers.append(float(p.replace("$", "").replace(",", "")))
            except ValueError:
                pass

        if len(numbers) >= 2:
            amount = numbers[0]

            if len(numbers) >= 3:  # custom ratio
                ratio = numbers[1]
                xrp_price = numbers[2]
            else:  # use live or fallback ratio
                ratio = live_tokens.get(detected_token) or FALLBACK_RATIOS[detected_token]
                xrp_price = numbers[1]

            if xrp_price <= 0 and live_xrp:
                xrp_price = live_xrp

            total = amount * ratio * xrp_price
            source = "Live" if live_tokens.get(detected_token) is not None else "Estimated"

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
        ratio = live_tokens.get(token) or FALLBACK_RATIOS[token]
        is_live = live_tokens.get(token) is not None
        value = ratio * xrp_price * DEFAULT_HOLDINGS[token]
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

    # Start health server
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start bot
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler(["calc", "bag", "live", "price"], calc))

    # Safer way to add the text handler (avoids backslash issues)
    text_filter = filters.TEXT & ~filters.COMMAND
    app.add_handler(MessageHandler(text_filter, calc))

    print("Capital Revival Calculator is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
