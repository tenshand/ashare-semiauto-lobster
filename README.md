# A股半自动策略

一套面向 **A股盘中信号提醒** 的半自动策略，核心思路是：
- 盘中持续轮询股票分钟线
- 基于均线、突破、止盈止损等规则生成信号
- 通过微信推送提醒
- 由人工在券商客户端手动执行买卖

> Semi-auto A-share signal system with intraday monitoring, signal generation, local state tracking, and WeChat notifications.

## Features

- A股分钟线监控
- 半自动买卖信号提醒
- 本地虚拟持仓状态管理
- 微信通知
- 收盘总结推送

## Project Structure

- `main.py`：主监控循环入口
- `strategy.py`：信号生成逻辑
- `data_provider.py`：行情数据获取
- `state_store.py`：本地状态与持仓记录
- `notifier.py`：通知发送
- `daily_summary.py`：A股收盘总结
- `run_main_loop.sh`：主程序启动脚本

## Runtime Layout

常驻服务：
- `ashare_semiauto_lobster.service`：A股盘中监控

定时任务：
- `ashare_daily_summary.timer`：A股收盘总结

## Upload Guide

建议上传：
- 所有 `.py` 源码
- `run_main_loop.sh`
- `README.md`
- `config.example.json`

不要上传：
- `config.json`
- `ashare_state.db`
- `daily_summary_latest.txt`
- `__pycache__/`

## Safety Notes

以下内容不建议公开：
- 实际通知目标
- Bot 账号信息
- 运行中的数据库
- 任何带有真实用户标识的配置

## Current Characteristics

- 定位是 **半自动提醒系统**，不是自动下单系统
- 信号生成后，由人工在券商客户端执行
- 本地维护虚拟持仓状态，用于后续信号判断和总结输出
- 适合盘中值守和收盘复盘结合使用
