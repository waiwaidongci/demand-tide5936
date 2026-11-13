"""滚动回测与预测。

历史口径（one_step）：逐日留出、每天只预测下一天，每步都能看到此前全部真值，
对应“逐日回测”的旧任务，函数保留以便复算旧结果。

现行口径（multi_step）：按任务预测天数 horizon 做滚动多步回测。每个回测起点
只用该起点之前的观测拟合一次，随后递推推出完整 horizon 天，段内不再用真值纠偏，
与“一次备货多天”的实际用法一致。各候选模型使用完全相同的起点与预测段比较，
按全部段、全部提前天数汇总的总体 MAE 选优。
"""
import math
from statistics import mean


def quantile(values, p):
    values = sorted(values)
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def predict(history, model, season, alpha=.5):
    """单步预测；供一步回测与多步递推共用。"""
    if model == 'seasonal_naive':
        return history[-season]
    level = history[0]
    for value in history[1:]:
        level = alpha * value + (1 - alpha) * level
    return level


def multi_step_predict(history, model, season, horizon, alpha=.5):
    """基于一份固定 history 递推 horizon 步；递推中只能使用预测值，不读真值。"""
    simulated = list(history)
    points = []
    for _ in range(horizon):
        point = predict(simulated, model, season, alpha)
        points.append(point)
        simulated.append(point)
    return points


CANDIDATES = [
    ('seasonal_naive', None),
    ('exponential_smoothing', .2),
    ('exponential_smoothing', .5),
    ('exponential_smoothing', .8),
]

MIN_OBS = 42
MIN_SEGMENTS = 2
MAX_HORIZON = 30


def _validate(values, horizon, season):
    if not 1 <= horizon <= MAX_HORIZON or not 2 <= season <= 30:
        raise ValueError('预测期1–30天，季节周期2–30天')
    if len(values) < MIN_OBS:
        raise ValueError(f'观测不足：至少{MIN_OBS}天，当前{len(values)}天')
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('需求必须为非负有限数')
    min_train = max(MIN_OBS, season * 3)
    return min_train


def _backtest_segments(n, horizon, min_train):
    """末端对齐、互不重叠的完整 horizon 段；每段起点前至少 min_train 个观测。"""
    segments = []
    end = n
    while end - horizon >= min_train:
        start = end - horizon
        segments.append((start, end))
        end = start
    segments.reverse()  # 按时间先后返回
    return segments


def forecast(values, horizon, season):
    """按任务预测天数做滚动多步回测并预测未来 horizon 天。"""
    min_train = _validate(values, horizon, season)
    n = len(values)
    segments = _backtest_segments(n, horizon, min_train)
    if len(segments) < MIN_SEGMENTS:
        need = min_train + MIN_SEGMENTS * horizon
        raise ValueError(
            '样本不足，无法完成滚动多步回测：'
            f'至少需要 {need} 天观测（{min_train} 天训练 + '
            f'{MIN_SEGMENTS} 个各 {horizon} 天的完整预测段），当前仅 {n} 天；'
            '请缩短预测天数或补齐观测后重建任务。'
        )

    per_candidate = []
    for model, alpha in CANDIDATES:
        seg_details = []
        # lead 维度索引 0..horizon-1，分别对应提前 1..horizon 天
        lead_abs = [0.0] * horizon
        lead_actual = [0.0] * horizon
        lead_count = [0] * horizon
        all_residuals = []
        for start, end in segments:
            preds = multi_step_predict(values[:start], model, season, horizon, alpha)
            actuals = values[start:end]
            rows = []
            for lead, (pred, actual) in enumerate(zip(preds, actuals), start=1):
                err = actual - pred
                rows.append({
                    'lead_day': lead,
                    'actual': round(actual, 2),
                    'predicted': round(pred, 2),
                    'error': round(err, 2),
                    'abs_error': round(abs(err), 2),
                })
                k = lead - 1
                lead_abs[k] += abs(err)
                lead_actual[k] += actual
                lead_count[k] += 1
                all_residuals.append(err)
            seg_details.append({
                'origin_index': start,          # 起点在序列中的下标（此前观测数）
                'start_index': start,
                'end_index': end,
                'predictions': rows,
                'segment_mae': round(sum(r['abs_error'] for r in rows) / horizon, 4),
                'segment_wape': round(
                    sum(r['abs_error'] for r in rows) / sum(actuals), 6
                ) if sum(actuals) else None,
            })
        lead_metrics = []
        for lead in range(1, horizon + 1):
            k = lead - 1
            lead_metrics.append({
                'lead_day': lead,
                'mae': round(lead_abs[k] / lead_count[k], 4),
                'wape': round(lead_abs[k] / lead_actual[k], 6) if lead_actual[k] else None,
                'samples': lead_count[k],
            })
        total_abs = sum(lead_abs)
        total_actual = sum(lead_actual)
        total_n = sum(lead_count)
        per_candidate.append({
            'model': model,
            'alpha': alpha,
            'mae': round(total_abs / total_n, 4),
            'wape': round(total_abs / total_actual, 6) if total_actual else None,
            'lead_metrics': lead_metrics,
            'segments': seg_details,
            'residuals': all_residuals,
        })

    # 总体 MAE 选优；所有候选的起点与预测段完全一致，口径可比
    best = min(range(len(per_candidate)), key=lambda i: per_candidate[i]['mae'])
    selected_block = per_candidate[best]
    residuals = selected_block.pop('residuals')

    comparisons = [{k: v for k, v in c.items() if k not in ('segments', 'residuals')}
                   for c in per_candidate]
    selected_summary = {k: v for k, v in selected_block.items() if k != 'lead_metrics'}

    # 分提前天数的残差分位带：每个 lead 用该提前天数的回测残差；
    # 残差过少（段数 <8）时退回总体分位，避免分位不稳定
    low_all, high_all = quantile(residuals, .1), quantile(residuals, .9)
    history = list(values)
    future = multi_step_predict(history, selected_block['model'], season, horizon,
                                selected_block['alpha'])
    lead_bounds = {}
    if len(segments) >= 8:
        for lead in range(1, horizon + 1):
            r = [r_ for seg in selected_block['segments']
                 for r_ in [row['error'] for row in seg['predictions']
                            if row['lead_day'] == lead]]
            lead_bounds[lead] = (quantile(r, .1), quantile(r, .9))
    points = []
    for lead, point in enumerate(future, start=1):
        low, high = lead_bounds.get(lead, (low_all, high_all))
        points.append({
            'predicted': round(point, 2),
            'lower': round(max(0, point + low), 2),
            'upper': round(max(0, point + high), 2),
        })

    return {
        'backtest_mode': 'multi_step',
        'selected': selected_summary,
        'comparisons': comparisons,
        'lead_metrics': selected_block['lead_metrics'],
        'backtest_segments': selected_block['segments'],
        'segment_count': len(segments),
        'horizon': horizon,
        'validation_days': len(segments) * horizon,
        'training_days': n,
        'min_training_days': min_train,
        'interval_note': (
            '滚动多步回测：每个起点仅用此前观测一次推出完整 '
            f'{horizon} 天，段内不以真值纠偏；经验带为入选模型各提前天数残差的 '
            '10%/90% 分位（段数不足 8 时用总体残差分位），未来覆盖率没有保证，'
            '未建模节假日冲击。'
        ),
        'points': points,
        'checksum': round(sum(values), 4),
    }


def forecast_one_step(values, horizon, season):
    """旧版逐日一步滚动回测，保留原口径用于复算历史任务结果。"""
    if not 1 <= horizon <= MAX_HORIZON or not 2 <= season <= 30:
        raise ValueError('预测期1–30天，季节周期2–30天')
    if len(values) < max(42, season * 3):
        raise ValueError('观测不足：至少42天且不少于3个季节周期')
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('需求必须为非负有限数')
    holdout = min(28, len(values) // 3)
    start = len(values) - holdout
    comparisons = []
    residual_sets = []
    for model, alpha in CANDIDATES:
        predictions = [predict(values[:i], model, season, alpha)
                       for i in range(start, len(values))]
        residuals = [y - p for y, p in zip(values[start:], predictions)]
        mae = mean(abs(e) for e in residuals)
        denom = sum(values[start:])
        comparisons.append({
            'model': model,
            'alpha': alpha,
            'mae': round(mae, 4),
            'wape': round(sum(abs(e) for e in residuals) / denom, 6) if denom else None,
        })
        residual_sets.append(residuals)
    best = min(range(len(comparisons)), key=lambda i: comparisons[i]['mae'])
    selected = comparisons[best]
    residuals = residual_sets[best]
    low, high = quantile(residuals, .1), quantile(residuals, .9)
    history = list(values)
    points = []
    for _ in range(horizon):
        point = predict(history, selected['model'], season, selected['alpha'])
        history.append(point)
        points.append({
            'predicted': round(point, 2),
            'lower': round(max(0, point + low), 2),
            'upper': round(max(0, point + high), 2),
        })
    return {
        'backtest_mode': 'one_step',
        'selected': selected,
        'comparisons': comparisons,
        'validation_days': holdout,
        'training_days': len(values),
        'interval_note': (
            '滚动回测残差的10%/90%经验分位带；未来覆盖率没有保证，未建模节假日冲击。'
            '（旧版逐日一步回测口径，每步可使用此前真值，偏乐观。）'
        ),
        'points': points,
        'checksum': round(sum(values), 4),
    }
