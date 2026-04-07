# T0 Backtest Sizing Carry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 T0 回测默认仓位调整为 3000+1000 股、金额上限 25 万，保留跨日未闭环分支，并把做 T 已实现净收益作为主指标重新回测工业富联。

**Architecture:** 继续沿用现有 `base_position + tactical_position` 模型，不引入新的 sizing mode。通过更新回测参数默认值、保留跨日历史、补充分离后的收益指标，最小化对现有策略核心的冲击。

**Tech Stack:** Python, pandas, pytest, backtest CLI

---

### Task 1: Lock Test Expectations

**Files:**
- Modify: `tests/unit/test_t0_backtest_simulator.py`
- Modify: `tests/unit/test_t0_backtest_cli.py`
- Test: `tests/unit/test_t0_backtest_simulator.py`

- [ ] **Step 1: Write the failing test**
- [ ] **Step 2: Run targeted tests and confirm the new expectations fail if behavior diverges**
- [ ] **Step 3: Keep only the expectations that reflect approved behavior**
- [ ] **Step 4: Re-run targeted tests after implementation**
- [ ] **Step 5: Commit**

### Task 2: Update Runtime Defaults And Metrics

**Files:**
- Modify: `src/strategy/core/params.py`
- Modify: `src/backtest/metrics.py`
- Modify: `src/backtest/cli.py`
- Test: `tests/unit/test_t0_backtest_cli.py`

- [ ] **Step 1: Adjust default base/tactical/max-trade-value parameters**
- [ ] **Step 2: Add summary fields for realized T PnL vs open-leg MTM**
- [ ] **Step 3: Ensure CLI summary writes the updated configuration**
- [ ] **Step 4: Run CLI unit tests**
- [ ] **Step 5: Commit**

### Task 3: Verify Carry Semantics And Re-Backtest

**Files:**
- Modify: `src/backtest/simulator.py` only if tests reveal a semantic mismatch
- Test: `tests/unit/test_t0_backtest_simulator.py`
- Output: `output/backtest_601138_20250407_20260407_*`

- [ ] **Step 1: Run simulator tests for cross-day branch carry**
- [ ] **Step 2: Change simulator only if the approved carry semantics are not already satisfied**
- [ ] **Step 3: Run targeted unit tests again**
- [ ] **Step 4: Execute industrial-fulian one-year backtest with updated defaults**
- [ ] **Step 5: Commit**
