import os
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# ---------- Flask health server (keeps Render awake) ----------
flask_app = Flask(__name__)

@flask_app.route("/")
@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# ---------- Bot settings ----------
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
    headers = {"User-Agent": "CapitalRevivalBot/1.6"}

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 *Capital Revival Calculator*\n\n"
        "Estimates values for RPR, ASC, PLR, BOX, STX & GRIM.\n\n"
        "*Simple ways to use:*\n\n"
        "1. Just type an XRP price\n"
        "   Example: `1.50`\n\n"
        "2. Custom bag with XRP price\n"
        "   Example: `50000 rpr 1.50`\n\n"
        "3. Custom bag with USD price per coin\n"
        "   Example: `50000 rpr $0.003`\n\n"
        "Type /help for all commands\n"
        "Type /info for explanation",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *Commands*\n\n"
        "/start – Welcome message\n"
        "/help – This help message\n"
        "/info – How the calculator works\n"
        "/calc – Use current live XRP price\n\n"
        "*How to type calculations:*\n\n"
        "• Just an XRP price\n"
        "  `1.50`\n\n"
        "• Custom bag + XRP price\n"
        "  `50000 rpr 1.50`\n\n"
        "• Custom bag + USD price per coin\n"
        "  `50000 rpr $0.003`\n\n"
        "• Advanced (custom ratio)\n"
        "  `50000 rpr @ 0.002 1.50`\n\n"
        "🟢 = Live price\n"
        "⚪ = Fallback ratio",
        parse_mode="Markdown"
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *How this calculator works*\n\n"
        "This bot estimates what RPR, ASC, PLR, BOX, STX and GRIM are worth.\n\n"
        "*Two price types:*\n\n"
        "🟢 *Live prices*\n"
        "Fetched in real-time from Dexscreener & XRPL.to when available.\n\n"
        "⚪ *Fallback ratios*\n"
        "Used only when live data cannot be fetched.\n\n"
        "*Notes:*\n"
        "• This is a projection tool, not financial advice.\n"
        "• Live prices change quickly on the XRPL DEX.\n"
        "• The 100,000 size is just an example portfolio.\n\n"
        "Data sources: CoinGecko (XRP), Dexscreener & XRPL.to",
        parse_mode="Markdown"
    )

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    lower_text = raw_text.lower()
    parts = lower_text.replace("@", " @ ").split()

    if parts and parts[0] in ["/calc", "/bag", "/live", "/price", "/start", "/help", "/info"]:
        parts = parts[1:]

    live_xrp = get_live_xrp_usd()
    live_tokens = get_live_token_prices_in_xrp()

    detected_token = None
    for p in parts:
        if p.upper() in FALLBACK_RATIOS:
            detected_token = p.upper()
            break

    if detected_token:
        numbers = []
        has_dollar = False
        for p in parts:
            if p.upper() == detected_token:
                continue
            clean = p.replace(",", "")
            if clean.startswith("$"):
                has_dollar = True
                clean = clean[1:]
            try:
                numbers.append(float(clean))
            except ValueError:
                pass

        if len(numbers) >= 1:
            custom_amount = numbers[0]

            if has_dollar and len(numbers) == 2:
                usd_price = numbers[1]
                total = custom_amount * usd_price
                await update.message.reply_text(
                    f"🎯 *Custom Calculation*\n\n"
                    f"• Amount: `{custom_amount:,.0f} {detected_token}`\n"
                    f"• Price per coin: `${usd_price:.4f} USD`\n\n"
                    f"💰 *Total Value: ${total:,.2f}*",
                    parse_mode="Markdown"
                )
                return

            if len(numbers) >= 3:
                custom_ratio = numbers[1]
                xrp_input = numbers[2]
            elif len(numbers) == 2:
                custom_ratio = live_tokens.get(detected_token) or FALLBACK_RATIOS[detected_token]
                xrp_input = numbers[1]
            else:
                await update.message.reply_text(
                    "Please use one of these formats:\n"
                    "`50000 rpr 1.50`\n"
                    "`50000 rpr $0.003`\n"
                    "`50000 rpr @ 0.002 1.50`"
                )
                return

            if xrp_input <= 0 and live_xrp:
                xrp_input = live_xrp

            total = custom_amount * custom_ratio * xrp_input
            source = "Live" if live_tokens.get(detected_token) else "Fallback"

            await update.message.reply_text(
                f"🎯 *Custom Bag Calculation*\n\n"
                f"• Amount: `{custom_amount:,.0f} {detected_token}`\n"
                f"• Ratio: `{custom_ratio:.6f} XRP` ({source})\n"
                f"• XRP Price: `${xrp_input:,.4f}`\n\n"
                f"💰 *Total Value: ${total:,.2f}*",
                parse_mode="Markdown"
            )
            return

    xrp_input = None
    if len(parts) == 1:
        try:
            xrp_input = float(parts[0].replace("$", "").replace(",", ""))
        except ValueError:
            pass

    if xrp_input is None or xrp_input <= 0:
        if live_xrp is None:
            await update.message.reply_text(
                "Could not fetch live XRP price.\nPlease type a number (example: `1.50`)."
            )
            return
        xrp_input = live_xrp
        mode = "Current Live XRP"
    else:
        mode = "Your Target XRP Price"

    lines = [f"📈 *XRP Price: ${xrp_input:,.4f}* ({mode})\n"]
    lines.append("💼 *Portfolio (100,000 of each token):*\n")

    total = 0.0
    for token in TOKEN_ORDER:
        ratio = live_tokens.get(token) or FALLBACK_RATIOS[token]
        is_live = live_tokens.get(token) is not None
        value = ratio * xrp_input * DEFAULT_HOLDINGS[token]
        total += value
        tag = "🟢" if is_live else "⚪"
        lines.append(f"{tag} *{token}*: `${value:,.2f}`  ({ratio:.6f} XRP)")

    lines.append(f"\n🚀 *Total Portfolio: ${total:,.2f}*")
    lines.append(
        "\n🟢 = Live price   ⚪ = Fallback ratio\n"
        "Examples:\n"
        "`1.50`  |  `50000 rpr 1.50`  |  `50000 rpr $0.003`"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

def main():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("Please set the TELEGRAM_BOT_TOKEN environment variable")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler(["calc", "bag", "live", "price"], calc))

    # IMPORTANT: no backslash before the \~
    text_filter = filters.TEXT & \~filters.COMMAND
    app.add_handler(MessageHandler(text_filter, calc))

    print("Capital Revival Calculator is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
