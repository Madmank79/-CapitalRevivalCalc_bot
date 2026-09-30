import os
import asyncio
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

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

TOKEN_ISSUERS = {
    "RPR":  "r3qWgpz2ry3BhcRJ8JE6rxM8esrfhuKp4R",
    "ASC":  "r3qWgpz2ry3BhcRJ8JE6rxM8esrfhuKp4R",
    "PLR":  "rNSYhWLhuHvmURwWbJPBKZMSPsyG5Qek17",
    "BOX":  "rhy4FUHtXrMZhbkBfeYvDv4nz6R7M4cu1t",
    "GRIM": "rHLRdLwXiBZSD53ZQz8ogGJz25LzNCCjSz",
}

def get_live_xrp_usd() -> float | None:
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "ripple", "vs_currencies": "usd"},
            timeout=8
        )
        return float(r.json()["ripple"]["usd"])
    except Exception:
        return None

def get_live_token_prices_in_xrp() -> dict:
    live = {t: None for t in TOKEN_ORDER}
    headers = {"User-Agent": "CapitalRevivalBot/1.3"}

    # Dexscreener
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

    # XRPL.to
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
        "Estimates the value of RPR, ASC, PLR, BOX, STX & GRIM based on an XRP price.\n\n"
        "*Quick Start:*\n"
        "• Type a number → e.g. `1.50`\n"
        "• Or type `/calc` to use the current live XRP price\n\n"
        "Type /help for all commands\n"
        "Type /info to understand how the calculator works",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *Available Commands*\n\n"
        "/start – Welcome message\n"
        "/help – Show this help message\n"
        "/info – How the calculator works\n"
        "/calc – Calculate using current live XRP price\n"
        "/live – Same as /calc\n"
        "/price – Same as /calc\n\n"
        "*Manual usage:*\n"
        "• Just type a number → `1.50`\n"
        "• Custom bag → `50000 rpr 1.50`\n"
        "• Custom ratio → `50000 rpr @ 0.0025 1.50`\n\n"
        "🟢 = Live market price\n"
        "⚪ = Fallback ratio (used when live data is unavailable)",
        parse_mode="Markdown"
    )

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *How this calculator works*\n\n"
        "This bot estimates what RPR, ASC, PLR, BOX, STX and GRIM would be worth at a given XRP price.\n\n"
        "*Two types of prices are used:*\n\n"
        "1. *Live prices* (🟢)\n"
        "   Fetched in real-time from XRPL sources (Dexscreener + XRPL.to) when available.\n\n"
        "2. *Fallback ratios* (⚪)\n"
        "   Fixed ratios used only when live data cannot be fetched.\n"
        "   These are approximate values based on historical/project data.\n\n"
        "*Important notes:*\n"
        "• This is a projection tool, not financial advice.\n"
        "• Live prices can change quickly on the XRPL DEX.\n"
        "• The 100,000 holding size is just an example for the portfolio view.\n"
        "• You can calculate any custom bag size using the formats above.\n\n"
        "Data sources: CoinGecko (XRP), Dexscreener & XRPL.to (tokens)",
        parse_mode="Markdown"
    )

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip().lower()
    clean_text = raw_text.replace("@", "")
    parts = clean_text.split()

    if parts and parts[0] in ["/calc", "/bag", "/live", "/price", "/start", "/help", "/info"]:
        parts = parts[1:]

    live_xrp = get_live_xrp_usd()
    live_tokens = get_live_token_prices_in_xrp()

    # Custom single-token bag
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
            custom_amount = numbers[0]
            if len(numbers) >= 3:
                custom_ratio = numbers[1]
                xrp_input = numbers[2]
            else:
                custom_ratio = live_tokens.get(detected_token) or FALLBACK_RATIOS[detected_token]
                xrp_input = numbers[1]

            if xrp_input <= 0 and live_xrp:
                xrp_input = live_xrp

            total = custom_amount * custom_ratio * xrp_input
            source = "Live" if live_tokens.get(detected_token) else "Fallback"

            await update.message.reply_text(
                f"🎯 *Custom Bag Calculation*\n\n"
                f"• Holding: `{custom_amount:,.0f} {detected_token}`\n"
                f"• Ratio: `{custom_ratio:.6f} XRP` ({source})\n"
                f"• Target XRP: `${xrp_input:,.4f}`\n\n"
                f"💰 *Total Value: ${total:,.2f}*",
                parse_mode="Markdown"
            )
            return

    # Normal portfolio view
    xrp_input = None
    if len(parts) == 1:
        try:
            xrp_input = float(parts[0].replace("$", "").replace(",", ""))
        except ValueError:
            pass

    if xrp_input is None or xrp_input <= 0:
        if live_xrp is None:
            await update.message.reply_text(
                "Could not fetch live XRP price right now.\nPlease type a number (example: `1.50`)."
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
        "Try: `50000 rpr 1.50` or `50000 rpr @ 0.0025 1.50`\n"
        "Type /info for explanation"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

def main():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("Please set the TELEGRAM_BOT_TOKEN environment variable")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler(["calc", "bag", "live", "price"], calc))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, calc))

    print("Capital Revival Calculator is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
