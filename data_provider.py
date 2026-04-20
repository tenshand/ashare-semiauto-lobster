from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class AkshareProvider:
    def __init__(self):
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency akshare. Install with `pip install -r requirements.txt`."
            ) from exc
        self.ak = ak
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_minute_bars(self, symbol: str, period: str, limit: int) -> list[Bar]:
        errors: list[str] = []
        try:
            df = self.ak.stock_zh_a_hist_min_em(symbol=symbol, period=period, adjust="")
            if df is not None and not df.empty:
                return self._bars_from_dataframe(symbol, df, limit)
            errors.append("em empty")
        except Exception as exc:
            errors.append(f"em:{exc}")

        try:
            return self._fetch_minute_bars_from_sina(symbol, period, limit)
        except Exception as exc:
            errors.append(f"sina:{exc}")

        try:
            return self._fetch_minute_bars_from_tencent(symbol, period, limit)
        except Exception as exc:
            errors.append(f"tencent:{exc}")

        raise RuntimeError(f"{symbol} 分钟线获取失败: {' | '.join(errors)}")

    def _bars_from_dataframe(self, symbol: str, df, limit: int) -> list[Bar]:
        normalized = df.rename(columns=self._build_rename_map(df.columns))
        required_columns = {"ts", "open", "high", "low", "close", "volume"}
        missing_columns = sorted(required_columns - set(normalized.columns))
        if missing_columns:
            raise RuntimeError(f"{symbol} minute data missing columns: {', '.join(missing_columns)}")

        bars: list[Bar] = []
        for row in normalized.tail(limit).to_dict("records"):
            bars.append(
                Bar(
                    ts=self._parse_ts(row["ts"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return bars

    def _fetch_minute_bars_from_sina(self, symbol: str, period: str, limit: int) -> list[Bar]:
        mapped = self._normalize_period(period)
        market_symbol = self._to_market_symbol(symbol)
        scale = mapped
        datalen = max(limit + 20, 120)
        url = (
            f"https://quotes.sina.cn/cn/api/openapi.php/CN_MarketDataService.getKLineData"
            f"?symbol={market_symbol}&scale={scale}&ma=no&datalen={datalen}"
        )
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("result", {}).get("data", [])
        if not rows:
            raise RuntimeError(f"新浪分钟线返回为空: {symbol}")

        bars: list[Bar] = []
        for row in rows[-limit:]:
            bars.append(
                Bar(
                    ts=self._parse_ts(row.get("day") or row.get("date") or row.get("time")),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or row.get("vol") or 0),
                )
            )
        if len(bars) < min(limit, 20):
            raise RuntimeError(f"新浪分钟线数据不足: {symbol} => {len(bars)}")
        return bars

    def _fetch_minute_bars_from_tencent(self, symbol: str, period: str, limit: int) -> list[Bar]:
        if str(period) != "5":
            raise RuntimeError(f"腾讯分钟线 fallback 仅支持 5 分钟周期，当前为 {period}")
        market_symbol = self._to_market_symbol(symbol)
        url = f"http://data.gtimg.cn/flashdata/hushen/minute/{market_symbol}.js"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        text = resp.text
        marker = 'min_data="'
        start = text.find(marker)
        if start == -1:
            raise RuntimeError(f"腾讯分钟线返回异常: {symbol}")
        payload = text[start + len(marker):]
        end = payload.rfind('"')
        if end != -1:
            payload = payload[:end]
        payload = payload.replace("\\n\\\n", "\n").replace("\\n\\", "\n").replace("\\n", "\n")
        lines = [line.strip() for line in payload.splitlines() if line.strip()]
        if not lines or not lines[0].startswith("date:"):
            raise RuntimeError(f"腾讯分钟线缺少 date 信息: {symbol}")
        date_str = lines[0].split(":", 1)[1].strip()
        trade_day = self._parse_trade_date(date_str)
        minute_rows = lines[1:]
        if len(minute_rows) < 5:
            raise RuntimeError(f"腾讯分钟线数据不足: {symbol}")

        minute_bars = []
        for row in minute_rows:
            parts = row.split()
            if len(parts) < 3:
                continue
            hhmm, price_raw, vol_raw = parts[:3]
            price = float(price_raw)
            volume = float(vol_raw)
            ts = datetime.combine(trade_day, datetime.strptime(hhmm, "%H%M").time())
            minute_bars.append((ts, price, volume))

        if len(minute_bars) < 5:
            raise RuntimeError(f"腾讯分钟线解析失败: {symbol}")

        bars: list[Bar] = []
        for idx in range(0, len(minute_bars), 5):
            chunk = minute_bars[idx:idx + 5]
            if len(chunk) < 5:
                continue
            prices = [item[1] for item in chunk]
            volumes = [item[2] for item in chunk]
            bars.append(
                Bar(
                    ts=chunk[-1][0],
                    open=prices[0],
                    high=max(prices),
                    low=min(prices),
                    close=prices[-1],
                    volume=sum(volumes),
                )
            )
        if len(bars) < 40:
            raise RuntimeError(f"腾讯 5 分钟数据不足: {symbol} => {len(bars)}")
        return bars[-limit:]

    @staticmethod
    def _normalize_period(period: str) -> str:
        period = str(period)
        if period not in {"1", "5", "15", "30", "60"}:
            raise RuntimeError(f"新浪分钟线不支持周期 {period}")
        return period

    @staticmethod
    def _to_market_symbol(symbol: str) -> str:
        s = str(symbol).lower()
        if s.startswith(("sh", "sz")):
            return s
        if s.startswith(("6", "9")):
            return f"sh{s}"
        return f"sz{s}"

    @staticmethod
    def _parse_trade_date(raw: str):
        raw = raw.strip()
        fmt = "%y%m%d" if len(raw) == 6 else "%Y%m%d"
        return datetime.strptime(raw, fmt).date()

    @staticmethod
    def _build_rename_map(columns) -> dict[str, str]:
        aliases = {
            "时间": "ts",
            "日期": "ts",
            "datetime": "ts",
            "open": "open",
            "开盘": "open",
            "high": "high",
            "最高": "high",
            "low": "low",
            "最低": "low",
            "close": "close",
            "收盘": "close",
            "volume": "volume",
            "成交量": "volume",
            "成交额": "amount",
        }
        rename_map: dict[str, str] = {}
        for column in columns:
            normalized = str(column).strip().lower()
            rename_map[column] = aliases.get(column, aliases.get(normalized, column))
        return rename_map

    @staticmethod
    def _parse_ts(raw: Any) -> datetime:
        if isinstance(raw, datetime):
            return raw
        value = str(raw).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
        return datetime.fromisoformat(value)
