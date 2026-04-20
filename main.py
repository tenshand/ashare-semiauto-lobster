#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from data_provider import AkshareProvider
from notifier import send_message
from state_store import StateStore
from strategy import build_signal

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "ashare_state.db"
CONFIG_PATH = ROOT / "config.json"


def load_config(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_trading_time(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    hm = now.strftime("%H:%M")
    return ("09:30" <= hm <= "11:30") or ("13:00" <= hm <= "15:00")


def qty_from_budget(price: float, budget_rmb: float) -> int:
    lots = int(budget_rmb // (price * 100))
    return max(0, lots * 100)


def process_symbol(store: StateStore, provider: AkshareProvider, config: dict[str, Any], symbol: str) -> bool:
    bars = provider.fetch_minute_bars(symbol, config["bar_period"], int(config["history_limit"]))
    open_position = store.get_open_position(symbol)
    signal = build_signal(symbol, bars, config, open_position)
    if not signal:
        return False

    dedupe_key = f"signal:{symbol}:{signal.signal_type}"
    dedupe_val = f"{bars[-1].ts.isoformat()}:{signal.price:.2f}"
    if store.get_state(dedupe_key) == dedupe_val:
        return False

    if signal.signal_type == "ENTRY":
        qty = qty_from_budget(signal.price, float(config["position_size_rmb"]))
        if qty <= 0:
            raise RuntimeError(f"{symbol} position_size_rmb too small for one lot")
        store.open_position(
            symbol=symbol,
            side="LONG",
            entry_price=signal.price,
            qty=qty,
            stop_loss=float(signal.stop_loss),
            take_profit=float(signal.take_profit),
            note="semi_auto_entry",
        )
        message = (
            f"{signal.message}\n"
            f"建议数量: {qty} 股\n"
            f"账户: 手动券商客户端执行\n"
            f"动作: 若你确认买入，请同步本地虚拟持仓状态"
        )
    else:
        qty = int(float(open_position["qty"])) if open_position else 0
        if open_position:
            store.close_position(int(open_position["id"]), signal.price, "semi_auto_exit")
        message = (
            f"{signal.message}\n"
            f"参考数量: {qty} 股\n"
            f"账户: 手动券商客户端执行\n"
            f"动作: 若你确认卖出，请确认本地虚拟持仓已平仓"
        )

    store.record_signal(symbol, signal.signal_type, signal.price, message)
    store.set_state(dedupe_key, dedupe_val)
    send_message(config, f"A股半自动信号 {symbol} {signal.signal_type}", message)
    print(message)
    return True


def run_once(store: StateStore, provider: AkshareProvider, config: dict[str, Any]) -> None:
    success_count = 0
    signal_count = 0

    for symbol in config["symbols"]:
        try:
            triggered = process_symbol(store, provider, config, symbol)
            success_count += 1
            if triggered:
                signal_count += 1
        except Exception as exc:
            text = (
                f"股票: {symbol}\n"
                f"性质: 程序处理异常，不是交易信号\n"
                f"原因: {exc}"
            )
            print(text)
            try:
                detail = (
                    f"{symbol} 本轮监控处理失败。\n"
                    f"这表示程序取数或计算异常，不代表买入/卖出信号。\n"
                    f"错误详情: {exc}"
                )
                send_message(config, f"A股策略运行异常 {symbol}", detail)
            except Exception:
                pass
        time.sleep(float(config.get("symbol_pause_seconds", 1)))

    print(f"A股监测正常，已检查 {success_count}/{len(config['symbols'])} 只股票，本轮触发 {signal_count} 条信号")


def main():
    config = load_config(Path(sys.argv[1]) if len(sys.argv) > 1 else CONFIG_PATH)
    store = StateStore(DB_PATH)
    provider = AkshareProvider()
    trading_sleep = float(config.get("trading_loop_seconds", 30))
    off_hours_sleep = float(config.get("off_hours_sleep_seconds", 300))
    announced_off_hours = False

    while True:
        now = datetime.now()
        if is_trading_time(now):
            if announced_off_hours:
                print(f"进入交易时段: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                announced_off_hours = False
            run_once(store, provider, config)
            time.sleep(trading_sleep)
            continue

        if not announced_off_hours:
            print(f"非交易时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
            announced_off_hours = True
        time.sleep(off_hours_sleep)


if __name__ == "__main__":
    main()
