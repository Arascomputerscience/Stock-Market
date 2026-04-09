if __name__ == "__main__":
    print("Starting Trading Bot...\n")
    run_bot()

import os
import alpaca_trade_api as tradeapi
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
BASE_URL = os.getenv("BASE_URL")

api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

# ---------------- CONFIG ----------------
watchlist = ["AAPL", "TSLA", "MSFT", "AMZN"]
portfolio = {symbol: 0 for symbol in watchlist}
price_data = {}
last_trade_time = {symbol: datetime.min for symbol in watchlist}

MAX_SHARES = 100
COOLDOWN = timedelta(days=1)


# ---------------- BST ----------------
class Node:
    def __init__(self, symbol, score):
        self.symbol = symbol
        self.score = score
        self.left = None
        self.right = None


class BST:
    def __init__(self):
        self.root = None

    def insert(self, symbol, score):
        def _insert(node, symbol, score):
            if not node:
                return Node(symbol, score)
            if score < node.score:
                node.left = _insert(node.left, symbol, score)
            else:
                node.right = _insert(node.right, symbol, score)
            return node

        self.root = _insert(self.root, symbol, score)

    def get_descending(self):
        result = []

        def traverse(node):
            if not node:
                return
            traverse(node.right)
            result.append(node.symbol)
            traverse(node.left)

        traverse(self.root)
        return result


# ---------------- DATA ----------------
def get_last_200_days_prices(symbol):
    end = datetime.now()
    start = end - timedelta(days=300)

    bars = api.get_bars(symbol, "1Day", start=start.isoformat(), end=end.isoformat()).df

    if bars.empty:
        return []

    return bars["close"].tolist()


def moving_average(prices, window):
    return sum(prices[-window:]) / window


# ---------------- MAIN BOT ----------------
def run_bot():
    bst = BST()
    current_time = datetime.now()

    # Step 1–4
    for symbol in watchlist:
        prices = get_last_200_days_prices(symbol)

        if len(prices) < 200:
            print(f"{symbol}: Not enough data")
            continue

        price_data[symbol] = prices

        short_ma = moving_average(prices, 50)
        long_ma = moving_average(prices, 200)

        prev_short_ma = sum(prices[-51:-1]) / 50
        prev_long_ma = sum(prices[-201:-1]) / 200

        momentum = short_ma - long_ma
        bst.insert(symbol, momentum)

    # Step 5
    sorted_stocks = bst.get_descending()

    # Step 6
    for symbol in sorted_stocks:
        shares = portfolio[symbol]
        last_trade = last_trade_time[symbol]

        if current_time - last_trade < COOLDOWN:
            print(f"{symbol}: Cooldown active")
            continue

        prices = price_data[symbol]

        short_ma = moving_average(prices, 50)
        long_ma = moving_average(prices, 200)

        prev_short_ma = sum(prices[-51:-1]) / 50
        prev_long_ma = sum(prices[-201:-1]) / 200

        # BUY
        if prev_short_ma <= prev_long_ma and short_ma > long_ma and shares == 0:
            if sum(portfolio.values()) + 50 <= MAX_SHARES:
                try:
                    api.submit_order(
                        symbol=symbol,
                        qty=50,
                        side="buy",
                        type="market",
                        time_in_force="gtc"
                    )
                    portfolio[symbol] = 50
                    last_trade_time[symbol] = current_time
                    print(f"{symbol}: BUY")
                except Exception as e:
                    print(f"{symbol}: Buy failed - {e}")

        # SELL
        elif prev_short_ma >= prev_long_ma and short_ma < long_ma and shares > 0:
            try:
                api.submit_order(
                    symbol=symbol,
                    qty=shares,
                    side="sell",
                    type="market",
                    time_in_force="gtc"
                )
                portfolio[symbol] = 0
                last_trade_time[symbol] = current_time
                print(f"{symbol}: SELL")
            except Exception as e:
                print(f"{symbol}: Sell failed - {e}")

        else:
            print(f"{symbol}: HOLD")

    print("\nPortfolio:", portfolio)


# ---------------- RUN ----------------
if __name__ == "__main__":
    run_bot()