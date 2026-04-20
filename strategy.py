from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Signal:
    symbol: str
    signal_type: str  # ENTRY / EXIT
    price: float
    stop_loss: float | None
    take_profit: float | None
    message: str


def _bar_value(bar: Any, key: str) -> float:
    if hasattr(bar, key):
        return float(getattr(bar, key))
    return float(bar[key])


def _ma(values: list[float], period: int) -> float:
    if len(values) < period:
        return sum(values) / max(1, len(values))
    return sum(values[-period:]) / period


def build_signal(symbol: str, bars: list[Any], config: dict[str, Any], open_position: Any) -> Signal | None:
    if not bars or len(bars) < 20:
        return None

    closes = [_bar_value(b, 'close') for b in bars]
    highs = [_bar_value(b, 'high') for b in bars]
    lows = [_bar_value(b, 'low') for b in bars]
    last = closes[-1]
    ma_fast = _ma(closes, int(config.get('ma_fast', 5)))
    ma_slow = _ma(closes, int(config.get('ma_slow', 20)))
    recent_high = max(highs[-10:])
    recent_low = min(lows[-10:])

    breakout_buffer = float(config.get('breakout_buffer_pct', 0.002))
    stop_loss_pct = float(config.get('stop_loss_pct', 0.02))
    take_profit_pct = float(config.get('take_profit_pct', 0.04))

    if open_position is None:
        if ma_fast > ma_slow and last >= recent_high * (1 - breakout_buffer):
            sl = last * (1 - stop_loss_pct)
            tp = last * (1 + take_profit_pct)
            return Signal(
                symbol=symbol,
                signal_type='ENTRY',
                price=last,
                stop_loss=sl,
                take_profit=tp,
                message=f'{symbol} 触发买入信号，现价 {last:.2f}，止损 {sl:.2f}，止盈 {tp:.2f}',
            )
        return None

    entry_price = float(open_position['entry_price'])
    stop_loss = float(open_position['stop_loss']) if open_position['stop_loss'] is not None else entry_price * (1 - stop_loss_pct)
    take_profit = float(open_position['take_profit']) if open_position['take_profit'] is not None else entry_price * (1 + take_profit_pct)

    if last <= stop_loss:
        return Signal(
            symbol=symbol,
            signal_type='EXIT',
            price=last,
            stop_loss=stop_loss,
            take_profit=take_profit,
            message=f'{symbol} 触发止损卖出信号，现价 {last:.2f}，止损位 {stop_loss:.2f}',
        )

    if last >= take_profit:
        return Signal(
            symbol=symbol,
            signal_type='EXIT',
            price=last,
            stop_loss=stop_loss,
            take_profit=take_profit,
            message=f'{symbol} 触发止盈卖出信号，现价 {last:.2f}，止盈位 {take_profit:.2f}',
        )

    if ma_fast < ma_slow and last <= recent_low * (1 + breakout_buffer):
        return Signal(
            symbol=symbol,
            signal_type='EXIT',
            price=last,
            stop_loss=stop_loss,
            take_profit=take_profit,
            message=f'{symbol} 趋势转弱，触发卖出信号，现价 {last:.2f}',
        )

    return None
