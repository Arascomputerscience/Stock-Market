import os
import logging
from datetime import datetime, timedelta

import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

# ---------------- LOAD ENV ----------------
load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID").strip()
API_SECRET = os.getenv("APCA_API_SECRET_KEY").strip()
BASE_URL = os.getenv("BASE_URL", "https://paper-api.alpaca.markets").strip()

api = tradeapi.REST(API_KEY, API_SECRET, BASE_URL, api_version='v2')

# ---------------- LOGGING ----------------
logging.basicConfig(
    filename="trading_log.txt",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

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
    try:
        bars = api.get_bars(symbol, "1Day", limit=250).df

        if bars.empty or "close" not in bars:
            logging.warning(f"{symbol}: No data returned")
            return []

        return bars["close"].dropna().tolist()

    except Exception as e:
        logging.error(f"{symbol}: Data fetch error - {e}")
        return []

def moving_average(prices, window):
    return sum(prices[-window:]) / window

# ---------------- MAIN BOT ----------------
def run_bot():
    logging.info("Bot started running")
    print("Bot started...\n")

    bst = BST()
    current_time = datetime.now()

    # STEP 1–4: DATA + METRICS
    for symbol in watchlist:
        print(f"Fetching data for {symbol}...")
        logging.info(f"Processing {symbol}")

        prices = get_last_200_days_prices(symbol)

        if len(prices) < 200:
            msg = f"{symbol}: Not enough data"
            print(msg)
            logging.warning(msg)
            continue

        price_data[symbol] = prices

        short_ma = moving_average(prices, 50)
        long_ma = moving_average(prices, 200)
        momentum = short_ma - long_ma

        print(f"{symbol} -> Short MA: {short_ma:.2f}, Long MA: {long_ma:.2f}, Momentum: {momentum:.2f}")
        logging.info(f"{symbol} metrics | short={short_ma:.2f}, long={long_ma:.2f}, momentum={momentum:.2f}")

        bst.insert(symbol, momentum)

    # STEP 5: SORT
    sorted_stocks = bst.get_descending()
    print("\nRanked Stocks (by momentum):", sorted_stocks)
    logging.info(f"Sorted stocks: {sorted_stocks}")

    # STEP 6: TRADING LOGIC
    for symbol in sorted_stocks:
        shares = portfolio[symbol]
        last_trade = last_trade_time[symbol]

        print(f"\nEvaluating {symbol}...")
        logging.info(f"Evaluating {symbol}")

        if current_time - last_trade < COOLDOWN:
            msg = f"{symbol}: Cooldown active"
            print(msg)
            logging.info(msg)
            continue

        prices = price_data.get(symbol, [])
        if len(prices) < 200:
            continue

        short_ma = moving_average(prices, 50)
        long_ma = moving_average(prices, 200)

        prev_short_ma = sum(prices[-51:-1]) / 50
        prev_long_ma = sum(prices[-201:-1]) / 200

        print(f"{symbol} Prev Short: {prev_short_ma:.2f}, Prev Long: {prev_long_ma:.2f}")
        print(f"{symbol} Curr Short: {short_ma:.2f}, Curr Long: {long_ma:.2f}")

        # BUY
        if prev_short_ma <= prev_long_ma and short_ma > long_ma and shares == 0:
            print(f"{symbol}: BUY SIGNAL TRIGGERED 🚀")
            logging.info(f"{symbol}: BUY signal")

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
                    print(f"{symbol}: EXECUTED BUY")
                    logging.info(f"{symbol}: BUY 50 shares")
                except Exception as e:
                    print(f"{symbol}: Buy failed - {e}")
                    logging.error(f"{symbol}: Buy failed - {e}")

        # SELL
        elif prev_short_ma >= prev_long_ma and short_ma < long_ma and shares > 0:
            print(f"{symbol}: SELL SIGNAL TRIGGERED 🔻")
            logging.info(f"{symbol}: SELL signal")

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
                print(f"{symbol}: EXECUTED SELL")
                logging.info(f"{symbol}: SELL all shares")
            except Exception as e:
                print(f"{symbol}: Sell failed - {e}")
                logging.error(f"{symbol}: Sell failed - {e}")

        else:
            print(f"{symbol}: HOLD (no crossover)")
            logging.info(f"{symbol}: HOLD")

    # STEP 7: SUMMARY
    total_shares = sum(portfolio.values())

    print("\n--- FINAL SUMMARY ---")
    print("Portfolio:", portfolio)
    print("Total Shares:", total_shares)

    logging.info(f"Final Portfolio: {portfolio}")
    logging.info(f"Total Shares: {total_shares}")


# ---------------- RUN ----------------
if __name__ == "__main__":
    print("Starting Trading Bot...\n")
    run_bot()