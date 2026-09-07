import asyncio
import logging
import sys
from typing import Optional
from agents.orchestrator import Orchestrator
from config.settings import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


class PersonalBot:
    def __init__(self):
        self.orchestrator = Orchestrator(config)
        self.market_agent = self.orchestrator.agents["market"]
        from tools.price_alert import PriceAlertEngine
        from tools.auto_trader import AutoTrader
        self.alerts = PriceAlertEngine(self.market_agent)
        self.trader = AutoTrader(self.market_agent)
        self.running = False

    async def start(self):
        await self.orchestrator.start()
        self.running = True
        logger.info("Personal Bot started!")

    async def stop(self):
        await self.orchestrator.stop()
        self.running = False
        logger.info("Personal Bot stopped!")

    async def process_command(self, command: str) -> str:
        cmd = command.strip().lower()

        if cmd.startswith("alert "):
            return await self._handle_alert(command)
        if cmd.startswith("remove alert "):
            alert_id = command.split("remove alert ")[1].strip()
            return "Alert removed" if self.alerts.remove_alert(alert_id) else "Alert not found"
        if cmd == "alert list" or cmd == "list alerts":
            alerts = self.alerts.list_alerts()
            if not alerts:
                return "No active alerts"
            return "\n".join(
                f"{a['alert_id']} | {a['symbol']} {a['condition']} {a['target_price']}"
                for a in alerts
            )

        if cmd.startswith("trade "):
            return await self._handle_trade(command)
        if cmd == "trader status" or cmd == "strategy status":
            return str(self.trader.get_status())

        if cmd.startswith("dse ") or cmd.startswith("check dse"):
            ticker = command.split("dse")[-1].strip().upper() or None
            result = await self.market_agent.execute(
                {"type": "check_dse", **({"ticker": ticker} if ticker else {})}
            )
            return str(result)

        return await self.orchestrator.process_user_command(command)

    async def _handle_alert(self, command: str) -> str:
        parts = command.split()
        if len(parts) < 5:
            return "Usage: alert BTCUSDT above 90000 [note]"
        symbol = parts[1].upper()
        condition = parts[2]
        if condition not in ("above", "below"):
            return "Condition must be 'above' or 'below'"
        try:
            target = float(parts[3])
        except ValueError:
            return "Target must be a number"
        note = " ".join(parts[4:])
        alert = self.alerts.add_alert(symbol, condition, target, note)
        return f"Alert set: {alert['symbol']} {alert['condition']} {alert['target_price']} (id: {alert['alert_id']})"

    async def _handle_trade(self, command: str) -> str:
        parts = command.split()
        if len(parts) < 2:
            return self._trade_help()
        sub = parts[1]
        if sub == "test":
            result = await self.market_agent.execute({"type": "set_test_mode", "test_mode": True})
            return str(result)
        if sub == "real":
            result = await self.market_agent.execute({"type": "set_test_mode", "test_mode": False})
            return str(result)
        if sub == "strategy":
            return self._trade_help()
        if sub == "run":
            symbol = parts[2].upper() if len(parts) > 2 else "BTCUSDT"
            strategy = parts[3] if len(parts) > 3 else "sma_cross"
            result = await self.trader.run_once(symbol, strategy)
            return str(result)
        return self._trade_help()

    def _trade_help(self) -> str:
        return (
            "Trade commands:\n"
            "- trade test  -> switch to PAPER mode (safe)\n"
            "- trade real  -> switch to REAL mode (danger!)\n"
            "- trade run BTCUSDT sma_cross\n"
            "- trade run BTCUSDT rsi_mean_reversion\n"
            "- trader status"
        )

    async def run_background_cycle(self):
        while self.running:
            try:
                result = await self.orchestrator.run_cycle()
                logger.info(f"Background cycle completed: {result}")
            except Exception as e:
                logger.error(f"Background cycle error: {e}")
            await asyncio.sleep(config.check_interval_seconds)


async def interactive_mode():
    bot = PersonalBot()
    await bot.start()

    print("\n" + "=" * 50)
    print("  Personal Bot - Interactive Mode")
    print("  Type 'help' for commands, 'quit' to exit")
    print("=" * 50 + "\n")

    try:
        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("\n>> ")
                )
            except EOFError:
                break

            if user_input.strip().lower() in ("quit", "exit", "q"):
                break
            elif user_input.strip().lower() == "help":
                print(get_help_text())
                continue
            elif not user_input.strip():
                continue

            result = await bot.process_command(user_input)
            print(f"\n{result}")

    finally:
        await bot.stop()


def get_help_text() -> str:
    return """
Available Commands:
  Facebook Ads (LIVE):
    - Create campaign [name]
    - Pause campaign [campaign_id]
    - Resume campaign [campaign_id]
    - Scale campaign [campaign_id]
    - List campaigns
    - Insights

  Facebook Posts:
    - Create post [message]      -> LIVE post করতে pages_manage_posts permission লাগবে

  WhatsApp:
    - Send WhatsApp [message]
    - Send template [name] to [phone]

  Market:
    - Check Binance [symbol]
    - Check DSE [ticker]     -> e.g. "dse BRACBANK", "dse" for full list
    - Add [symbol] to watchlist
    - Analyze trend [symbol]

  Price Alerts:
    - alert BTCUSDT above 90000 [note]
    - alert BTCUSDT below 75000
    - alert list
    - remove alert [alert_id]

  Auto Trader:
    - trade test               -> PAPER mode (safe)
    - trade real               -> REAL mode (danger!)
    - trade run BTCUSDT sma_cross
    - trade run ETHUSDT rsi_mean_reversion
    - trader status

  Algorithm:
    - Analyze performance
    - Detect anomalies
    - Get recommendations

  System:
    - help    : Show this help
    - quit    : Exit the bot
"""


async def main():
    if len(sys.argv) > 1:
        command = " ".join(sys.argv[1:])
        bot = PersonalBot()
        await bot.start()
        result = await bot.process_command(command)
        print(result)
        await bot.stop()
    else:
        await interactive_mode()


if __name__ == "__main__":
    asyncio.run(main())
