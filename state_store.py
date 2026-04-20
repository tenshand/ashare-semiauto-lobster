#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            create table if not exists positions (
                id integer primary key autoincrement,
                symbol text not null,
                side text not null,
                entry_price real not null,
                qty integer not null,
                stop_loss real,
                take_profit real,
                status text not null default 'open',
                note text,
                created_at datetime default current_timestamp,
                closed_at datetime,
                exit_price real,
                exit_reason text
            );

            create table if not exists signals (
                id integer primary key autoincrement,
                symbol text not null,
                signal_type text not null,
                price real not null,
                message text not null,
                notify_status text not null default 'new',
                created_at datetime default current_timestamp
            );

            create table if not exists bot_state (
                key text primary key,
                value text not null
            );
            """
        )
        self.conn.commit()

    def get_open_position(self, symbol: str):
        return self.conn.execute(
            "select * from positions where symbol=? and status='open' order by id desc limit 1",
            (symbol,),
        ).fetchone()

    def open_position(self, symbol: str, side: str, entry_price: float, qty: int,
                      stop_loss: float | None, take_profit: float | None, note: str = ""):
        self.conn.execute(
            "insert into positions(symbol, side, entry_price, qty, stop_loss, take_profit, note) values(?,?,?,?,?,?,?)",
            (symbol, side, entry_price, qty, stop_loss, take_profit, note),
        )
        self.conn.commit()

    def close_position(self, position_id: int, exit_price: float, exit_reason: str = ""):
        self.conn.execute(
            "update positions set status='closed', closed_at=current_timestamp, exit_price=?, exit_reason=? where id=?",
            (exit_price, exit_reason, position_id),
        )
        self.conn.commit()

    def record_signal(self, symbol: str, signal_type: str, price: float, message: str):
        self.conn.execute(
            "insert into signals(symbol, signal_type, price, message) values(?,?,?,?)",
            (symbol, signal_type, price, message),
        )
        self.conn.commit()

    def get_state(self, key: str):
        row = self.conn.execute("select value from bot_state where key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str):
        self.conn.execute(
            "insert into bot_state(key, value) values(?, ?) on conflict(key) do update set value=excluded.value",
            (key, value),
        )
        self.conn.commit()
