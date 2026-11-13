# 002 回测口径升级：逐日一步 → 按预测天数滚动多步

## 背景

日配业务一次备货多天（常见 horizon=14）。旧口径逐日留出、每步只预测次日，
每一步都能使用此前全部真值，相当于每天获得一次真值纠偏，无法反映多步递推中
误差累积，回测误差比实际备货偏乐观。

## 变更范围

仅变更 `forecast_runs.result` 的 JSON 内容与计算函数，**无表结构变更，无需 SQL 迁移**；
`forecast_points`、序列、发布等表均不受影响。

- `services/forecast_algorithm.py`
  - `forecast(values, horizon, season)`：现行口径，滚动多步回测，结果带
    `backtest_mode="multi_step"`。
  - `forecast_one_step(values, horizon, season)`：保留旧逐日一步口径，结果带
    `backtest_mode="one_step"`，用于复算与对照，不再被任务流程调用。
- 多步结果新增字段：`lead_metrics`（分提前天数 MAE/WAPE/样本数）、
  `backtest_segments`（各段逐日预测、真值、误差、段 MAE/WAPE）、
  `segment_count`、`horizon`、`min_training_days`；`validation_days` 改为
  `segment_count × horizon` 的回测覆盖天数。
- 旧结果 JSON 中不存在 `backtest_mode`，前端与导出按缺省 `one_step` 处理，
  原有 `selected/comparisons/validation_days/training_days/interval_note` 语义不变。

## 样本要求与失败语义

每段起点前至少 `max(42, 3×season)` 个观测，且至少 2 个互不重叠的完整 horizon 段，
即总观测不少于 `max(42, 3×season) + 2×horizon`。不满足时任务置为 failed，
错误信息给出所需天数与当前天数，不产出候选排名。

## 升级后历史数据的处理

1. 已完成的旧任务保持原结果可查看：结果页显示“旧版一步回测”标识与偏乐观说明，
   CSV 导出保留候选误差汇总。
2. 旧任务不会自动重算；需要多步口径时在实验页用相同参数重建任务，
   旧记录与发布档案继续保留以便追溯。
3. 新任务一律写入 `backtest_mode="multi_step"` 结构。
