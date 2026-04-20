#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股收盘总结生成并推送。"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

WORKDIR = Path('/root/.openclaw/workspace')
CONFIG_PATH = WORKDIR / 'ashare_semiauto_lobster' / 'config.json'
OUTPUT_PATH = WORKDIR / 'ashare_semiauto_lobster' / 'daily_summary_latest.txt'

HOLDINGS = [
    {'code': '300857.SZ', 'name': '协创数据', 'cost': 230.0, 'qty': 200},
    {'code': '600621.SH', 'name': '华鑫股份', 'cost': 14.7, 'qty': 2000},
]
KEY_LEVELS = {
    '300857.SZ': {'support': 204.20, 'pivot': 208.00, 'pressure': 214.23},
}


def fetch_sina_quotes(codes: list[str]) -> dict[str, dict]:
    sina_codes = []
    for code in codes:
        if code.endswith('.SH'):
            sina_codes.append('sh' + code[:-3])
        elif code.endswith('.SZ'):
            sina_codes.append('sz' + code[:-3])
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    req = urllib.request.Request(url, headers={
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0',
    })
    out: dict[str, dict] = {}
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode('gb2312', errors='ignore')
    for line in content.splitlines():
        if '=' not in line:
            continue
        key = line.split('=')[0].split('_')[-1]
        raw = line.split('=', 1)[1].strip().strip(';').strip('"')
        if not raw:
            continue
        parts = raw.split(',')
        if len(parts) < 10:
            continue
        try:
            out[key] = {
                'name': parts[0],
                'open': float(parts[1] or 0),
                'pre_close': float(parts[2] or 0),
                'close': float(parts[3] or 0),
                'high': float(parts[4] or 0),
                'low': float(parts[5] or 0),
                'vol': float(parts[8] or 0),
                'amount': float(parts[9] or 0),
            }
        except ValueError:
            continue
    return out


def pct(a: float, b: float) -> float:
    return ((a / b) - 1) * 100 if b else 0.0


def analyze_stock(h: dict, q: dict) -> list[str]:
    current = q['close'] or q['pre_close']
    prev = q['pre_close']
    open_price = q['open'] or prev
    intraday_pct = pct(current, open_price)
    day_pct = pct(current, prev)
    pnl = (current - h['cost']) * h['qty']
    pnl_pct = pct(current, h['cost'])
    turnover = q['amount'] / 1e8
    amplitude = pct(q['high'], q['low']) if q['low'] else 0.0

    lines = [
        f"{h['name']}({h['code']})",
        f"- 收盘价：{current:.2f}，较昨收 {day_pct:+.2f}% ，较今开 {intraday_pct:+.2f}%",
        f"- 持仓：{h['qty']}股，成本：{h['cost']:.3f}，浮盈亏：{pnl:+,.0f}元 ({pnl_pct:+.2f}%)",
        f"- 日内区间：{q['low']:.2f}-{q['high']:.2f}，振幅：{amplitude:.2f}% ，成交额：{turnover:.2f}亿",
    ]

    if current >= open_price and current >= prev:
        lines.append("- 结构判断：收盘强于开盘且站在昨收上方，尾盘承接不弱。")
    elif current < open_price and current < prev:
        lines.append("- 结构判断：收盘弱于开盘且压在昨收下方，短线抛压仍在。")
    else:
        lines.append("- 结构判断：日内有拉扯，收盘偏中性，暂看震荡。")

    if h['code'] == '300857.SZ':
        lv = KEY_LEVELS[h['code']]
        if current <= lv['support']:
            lines.append(f"- 关键位：已逼近/跌破防守位 {lv['support']:.2f}，这里是明天最重要的止守线。")
        elif current < lv['pivot']:
            lines.append(f"- 关键位：收盘落在中轴 {lv['pivot']:.2f} 下方，修复力度还不够。")
        elif current < lv['pressure']:
            lines.append(f"- 关键位：收盘卡在中轴 {lv['pivot']:.2f} 一线，上方先看 {lv['pressure']:.2f} 压力。")
        else:
            lines.append(f"- 关键位：已重新站上 {lv['pressure']:.2f}，短线情绪转强。")
        lines.append(f"- 明日跟踪：{lv['support']:.2f} 不破可继续拿，重新放量站稳 {lv['pressure']:.2f} 才算真正转强。")
    elif h['code'] == '600621.SH':
        if day_pct > 1:
            lines.append("- 明日跟踪：若继续放量上攻，可看反弹延续；若缩量冲高回落，仍按弱反处理。")
        else:
            lines.append("- 明日跟踪：先看 5 日线附近能否站稳，站不稳就以防守、减幻想为主。")

    return lines


def build_summary() -> str:
    quotes = fetch_sina_quotes([h['code'] for h in HOLDINGS])
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"A股收盘详细总结 | {now}", '']
    total_cost = 0.0
    total_value = 0.0
    total_pnl = 0.0
    gainers = 0
    losers = 0
    detail_blocks: list[str] = []
    for h in HOLDINGS:
        key = ('sh' if h['code'].endswith('.SH') else 'sz') + h['code'][:-3]
        q = quotes.get(key)
        if not q:
            detail_blocks.append(f"{h['name']}({h['code']})\n- 行情获取失败\n")
            continue
        current = q['close'] or q['pre_close']
        day_pct = pct(current, q['pre_close'])
        pnl = (current - h['cost']) * h['qty']
        total_cost += h['cost'] * h['qty']
        total_value += current * h['qty']
        total_pnl += pnl
        if day_pct >= 0:
            gainers += 1
        else:
            losers += 1
        detail_blocks.append('\n'.join(analyze_stock(h, q)) + '\n')

    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0.0
    lines.extend([
        '一、整体持仓分析',
        f"- 持仓标的：{len(HOLDINGS)}只，上涨 {gainers} 只，下跌 {losers} 只",
        f"- 总成本：{total_cost:,.0f}元",
        f"- 总市值：{total_value:,.0f}元",
        f"- 总浮盈亏：{total_pnl:+,.0f}元 ({total_pnl_pct:+.2f}%)",
        '',
        '二、个股详细分析',
    ])
    lines.extend(detail_blocks)
    focus = next((h for h in HOLDINGS if h['code'] == '300857.SZ'), None)
    focus_quote = quotes.get('sz300857') if focus else None
    ai_lines = ['三、AI智能分析及建议']
    if focus and focus_quote:
        current = focus_quote['close'] or focus_quote['pre_close']
        prev = focus_quote['pre_close']
        open_price = focus_quote['open'] or prev
        lv = KEY_LEVELS[focus['code']]
        day_pct = pct(current, prev)
        intraday_pct = pct(current, open_price)
        if current >= lv['pressure']:
            ai_lines.append(
                f"- 协创数据今天收在 {current:.2f}，已经站上关键压力位 {lv['pressure']:.2f}，情绪明显转强，但涨幅过大后次日更要防冲高回落。"
            )
        elif current >= lv['pivot']:
            ai_lines.append(
                f"- 协创数据今天收在 {current:.2f}，重新回到中轴 {lv['pivot']:.2f} 上方，短线修复成立，但还需要继续确认承接。"
            )
        else:
            ai_lines.append(
                f"- 协创数据今天收在 {current:.2f}，仍在中轴 {lv['pivot']:.2f} 下方，当前更像弱修复，防守位 {lv['support']:.2f} 仍是明天第一观察点。"
            )
        ai_lines.append(
            f"- 日内相对昨收 {day_pct:+.2f}% 、相对开盘 {intraday_pct:+.2f}% ，明天不要只看涨跌幅，更要看能否继续站稳 {lv['pressure']:.2f} 一线。"
        )
    else:
        ai_lines.append('- 协创数据今日行情未完整获取，建议以关键位和次日承接强弱为主。')

    ai_lines.extend([
        '',
        '四、明日关键价',
        '- 协创数据：204.20 / 208.00 / 214.23',
        '',
        '五、执行建议',
        '- 协创数据：不破 204.20 可继续观察，跌破则按防守优先；若高开冲高，重点看能否放量站稳 214.23 之上。',
    ])
    lines.extend(ai_lines)
    return '\n'.join(lines).strip() + '\n'


def send_openclaw_message(text: str) -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    oc = config['notify']['openclaw']
    cmd = [
        oc.get('binary', 'openclaw'), 'message', 'send',
        '--channel', oc['channel'],
        '--target', oc['target'],
        '--account', oc['account'],
        '--message', text,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"send failed rc={proc.returncode}: {(proc.stderr or proc.stdout).strip()}")
    if 'Message ID:' not in (proc.stdout + proc.stderr):
        raise RuntimeError(f"send returned without message id: {(proc.stdout + proc.stderr).strip()}")


def main() -> int:
    text = build_summary()
    OUTPUT_PATH.write_text(text, encoding='utf-8')
    if '--send' in sys.argv:
        send_openclaw_message(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
