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
    "RPR": 0.00202,
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
    
    # Check XRPL.to tokens endpoint with comprehensive key matching
    try:
        r = requests.get("https://api.xrpl.to/v1/tokens?limit=200", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            tokens = data.get("tokens", data) if isinstance(data, dict) else data
            if isinstance(tokens, list):
                for item in tokens:
                    # Check multiple possible keys for symbol and price
                    symbol = str(item.get("name") or item.get("currency") or item.get("symbol") or item.get("code") or "").upper()
                    price = (
                        item.get("exch") or 
                        item.get("price") or 
                        item.get("price_xrp") or 
                        item.get("rate") or 
                        item.get("buy_price")
                    )
                    for t in TOKEN_ORDER:
                        if t == symbol or t in symbol:
                            if price is not None:
                                try:
                                    live[t] = float(price)
                                except ValueError:
                                    pass
    except Exception:
        pass

    # Fallback search query for any still missing
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
        "📊 *Capital Revival Calculator Guide*\n\n"
        "Calculate potential bag values using live market data from XRPL.to & CoinGecko.\n\n"
        "💡 *How to use commands:*\n"
        "• **Just XRP price:** `2.50`\n"
        "• **Custom Ratio & Target:** `50000 rpr @ 0.002 1.50`",
        parse_mode="Markdown"
    )

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip().lower()
    clean_text = raw_text.replace("@", "")
    parts = clean_text.split()

    if parts and parts[0] in ["/calc", "/bag", "/live", "/price"]:
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
        for p in parts:
            if p.upper() == detected_token:
                continue
            try:
                num = float(p.replace("$", "").replace(",", ""))
                numbers.append(num)
            except ValueError:
                pass

        if len(numbers) >= 2:
            custom_amount = numbers[0]
            if len(numbers) == 3:
                custom_ratio = numbers[1]
                xrp_input = numbers[2]
            else:
                # If ratio wasn't explicitly typed, grab live market rate or fallback
                custom_ratio = live_tokens.get(detected_token) or FALLBACK_RATIOS[detected_token]
                xrp_input = numbers[1]

            if live_xrp and (xrp_input <= 0):
                xrp_input = live_xrp

            token_usd_price = custom_ratio * xrp_input
            total_bag_usd = custom_amount * token_usd_price

            await update.message.reply_text(
                f"🎯 *Custom Bag Calculation*\n\n"
                f"• *Holding:* {custom_amount:,.2f} {detected_token}\n"
                f"• *Token Ratio:* {custom_ratio:.6f} XRP\n"
                f"• *Target XRP:* ${xrp_input:,.4f}\n\n"
                f"💰 **Total Value: ${total_bag_usd:,.2f}**\n\n"
                f"*(Data: XRPL.to & CoinGecko)*",
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
            await update.message.reply_text("Could not fetch live XRP price. Please enter a valid number (e.g., `1.50`).", parse_mode="Markdown")
            return
        xrp_input = live_xrp
        mode = "Current Live Price"
    else:
        mode = "Target Projection"

    lines = [f"📈 *XRP Price:* ${xrp_input:,.4f} ({mode})\n"]
    lines.append("💼 *Portfolio Breakdown (100k per token):*")
    
    total_portfolio_usd = 0
    for token in TOKEN_ORDER:
        token_xrp_price = live_tokens.get(token) or FALLBACK_RATIOS[token]
        holding_amount = DEFAULT_HOLDINGS[token]
        holding_usd = token_xrp_price * xrp_input * holding_amount
        total_portfolio_usd += holding_usd
        
        lines.append(f"• *{token}*: ${holding_usd:,.2f}  _({token_xrp_price:.6f} XRP)_")

    lines.append(f"\n🚀 **Total Portfolio: ${total_portfolio_usd:,.2f}**")
    lines.append(
        "\n━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Try custom format:*\n"
        "• `50000 rpr @ 0.002 1.50`"
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

    print("Bag calculator bot is running with enhanced API field matching...")
    
    try:
        app.run_polling()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        app.run_polling()

if __name__ == "__main__":
    main()
