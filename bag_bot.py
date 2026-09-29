import os
import asyncio
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TELEGRAM_BOT_TOKEN = "8843510657AAGzWuofGxxMcDsr-DKhHLq"

DEFAULT_HOLDINGS = {
    "RPR": 100000,
    "ASC": 100000,
    "PLR": 100000,
    "BOX": 100000,
    "STX": 100000,
    "GRIM": 100000,
}

FALLBACK_RATIOS = {
    "RPR": 0.0031,
    "ASC": 0.00037,
    "PLR": 0.00055,
    "BOX": 0.00015,
    "STX": 0.000004,
    "GRIM": 0.0042,
}

TOKEN_ORDER = ["RPR", "ASC", "PLR", "BOX", "STX", "GRIM"]

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
    headers = {"User-Agent": "CapitalRevivalBot/1.0"}
    try:
        r = requests.get("https://api.xrpl.to/v1/tokens?limit=150&sort=vol24hxrp", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            tokens = data.get("tokens", data) if isinstance(data, dict) else data
            for item in tokens:
                symbol = str(item.get("name") or item.get("currency") or item.get("symbol") or "").upper()
                price = item.get("exch") or item.get("price") or item.get("price_xrp") or item.get("rate")
                if symbol in live and price is not None:
                    live[symbol] = float(price)
    except Exception:
        pass

    for token in TOKEN_ORDER:
        if live[token] is None:
            try:
                sr = requests.get("https://api.xrpl.to/v1/search", params={"q": token}, headers=headers, timeout=5)
                if sr.status_code == 200:
                    sdata = sr.json()
                    matches = sdata.get("tokens", sdata.get("data", sdata)) if isinstance(sdata, dict) else sdata
                    if isinstance(matches, list):
                        for m in matches:
                            msymbol = str(m.get("name") or m.get("currency") or m.get("symbol") or "").upper()
                            mprice = m.get("exch") or m.get("price") or m.get("price_xrp") or m.get("rate")
                            if token in msymbol and mprice is not None:
                                live[token] = float(mprice)
                                break
            except Exception:
                pass
    return live

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 *Capital Revival Dual-Driver Calculator*\n\n"
        "Calculate bag value accounting for **both** XRP price movement **and** individual token ratio shifts!\n\n"
        "**Flexible Inputs:**\n"
        "1. *General Portfolio Check:* Send a target XRP price like `2.50`\n"
        "2. *Specific Custom Bag:* Send `Amount Token TargetXRP` (e.g., `50000 RPR 3.00`)\n"
        "3. *Advanced Dual-Driver:* Send `Amount Token TargetRatio TargetXRP`\n"
        "   _Example:_ `50000 RPR 0.0050 3.00` (Calculates 50,000 RPR if its ratio grows to `0.0050 XRP` *and* XRP hits `$3.00`).",
        parse_mode="Markdown"
    )

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    parts = text.split()

    if parts and parts[0] in ["/calc", "/bag", "/live", "/price"]:
        parts = parts[1:]

    custom_amount = None
    custom_token = None
    custom_ratio = None
    xrp_input = None

    live_xrp = get_live_xrp_usd()
    live_tokens = get_live_token_prices_in_xrp()

    # Pattern parsing based on number of arguments provided
    if len(parts) >= 4:
        # e.g. 50000 rpr 0.0050 3.00
        try:
            custom_amount = float(parts[0].replace(",", ""))
            custom_token = parts[1].upper()
            custom_ratio = float(parts[2])
            xrp_input = float(parts[3].replace("$", "").replace(",", ""))
        except ValueError:
            pass
    elif len(parts) == 3:
        # e.g. 50000 rpr 3.00 (uses live/fallback ratio)
        try:
            custom_amount = float(parts[0].replace(",", ""))
            custom_token = parts[1].upper()
            xrp_input = float(parts[2].replace("$", "").replace(",", ""))
        except ValueError:
            pass
    elif len(parts) == 1:
        try:
            xrp_input = float(parts[0].replace("$", "").replace(",", ""))
        except ValueError:
            pass

    if xrp_input is None or xrp_input <= 0:
        if live_xrp is None:
            await update.message.reply_text("Could not fetch live XRP price. Please enter a valid number (e.g., `2.00`).", parse_mode="Markdown")
            return
        xrp_input = live_xrp
        mode = "Current Live Price"
    else:
        mode = "Target Projection"

    # Handle custom token calculation
    if custom_amount is not None and custom_token in FALLBACK_RATIOS:
        if custom_ratio is None:
            custom_ratio = live_tokens.get(custom_token) or FALLBACK_RATIOS[custom_token]

        token_usd_price = custom_ratio * xrp_input
        total_bag_usd = custom_amount * token_usd_price

        await update.message.reply_text(
            f"🎯 *Custom Dual-Driver Bag Calculation*\n\n"
            f"• *Token Bag:* {custom_amount:,.0f} {custom_token}\n"
            f"• *Token-to-XRP Ratio:* {custom_ratio:.6f} XRP per {custom_token}\n"
            f"• *Target XRP Price:* ${xrp_input:,.4f}\n"
            f"• *Projected Token USD Price:* ${token_usd_price:,.4f}\n\n"
            f"💰 **Total Bag Value: ${total_bag_usd:,.2f}**\n\n"
            f"_(Data powered by XRPL.to & CoinGecko)_",
            parse_mode="Markdown"
        )
        return

    # Default full portfolio matrix output
    lines = [f"📈 *XRP Price:* ${xrp_input:,.4f} ({mode})\n"]
    lines.append("💼 *Portfolio Breakdown (Default 100k held per token):*")
    
    total_portfolio_usd = 0
    for token in TOKEN_ORDER:
        token_xrp_price = live_tokens.get(token) or FALLBACK_RATIOS[token]
        holding_amount = DEFAULT_HOLDINGS[token]
        holding_usd = token_xrp_price * xrp_input * holding_amount
        total_portfolio_usd += holding_usd
        
        lines.append(f"• *{token}*: ${holding_usd:,.2f}  _({token_xrp_price:.6f} XRP)_")

    lines.append(f"\n🚀 **Total Portfolio Value: ${total_portfolio_usd:,.2f}**")
    lines.append(
        "\nℹ️ *Custom Formats:*\n"
        "• Specific bag: `50000 RPR 3.00`\n"
        "• Custom ratio + XRP target: `50000 RPR 0.0050 3.00`"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

def main():
    token = TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("Please set your bot token")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["calc", "bag", "live", "price"], calc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, calc))

    print("Dual-driver bag calculator bot is running...")
    
    try:
        app.run_polling()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app.run_polling()

if __name__ == "__main__":
    main()
