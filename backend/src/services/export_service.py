import io
import csv
from fastapi import HTTPException
from .run_service import detail


def export_csv(db, run_id):
    run = detail(db, run_id)
    if run['status'] != 'completed':
        raise HTTPException(409, '预测尚未完成')
    result = run['result'] or {}
    mode = result.get('backtest_mode', 'one_step')
    stream = io.StringIO()
    stream.write('﻿')
    writer = csv.writer(stream)
    writer.writerow(['序列', '日期', '点预测', '经验下界', '经验上界', '模型', '口径说明'])
    for p in run['points']:
        writer.writerow([
            run['series']['name'], p['day'], p['predicted'], p['lower'], p['upper'],
            result.get('selected', {}).get('model'), result.get('interval_note'),
        ])

    if mode == 'multi_step':
        writer.writerow([])
        writer.writerow([
            f"滚动多步回测明细（{result.get('segment_count')} 段 × "
            f"{result.get('horizon')} 天，每段起点仅用此前观测，段内不纠偏）"
        ])
        writer.writerow(['回测段', '段起点(此前观测天数)', '提前天数', '真值', '预测', '误差(真值-预测)', '绝对误差'])
        for idx, seg in enumerate(result.get('backtest_segments', []), start=1):
            for row in seg.get('predictions', []):
                writer.writerow([
                    f'第{idx}段', seg.get('origin_index'), row['lead_day'],
                    row['actual'], row['predicted'], row['error'], row['abs_error'],
                ])
        writer.writerow([])
        writer.writerow(['分提前天数误差（入选模型）'])
        writer.writerow(['提前天数', 'MAE', 'WAPE', '样本段数'])
        for m in result.get('lead_metrics', []):
            writer.writerow([
                m['lead_day'], m['mae'],
                '无实际需求分母' if m['wape'] is None else m['wape'], m['samples'],
            ])
        writer.writerow([])
        writer.writerow(['候选总体误差（同起点同预测段，按总体MAE选优）'])
        writer.writerow(['模型', 'alpha', '总体MAE', '总体WAPE'])
        for c in result.get('comparisons', []):
            writer.writerow([
                c['model'], c['alpha'] if c['alpha'] is not None else '',
                c['mae'], '无实际需求分母' if c['wape'] is None else c['wape'],
            ])
    else:
        writer.writerow([])
        writer.writerow(['旧版逐日一步滚动回测：每步仅预测次日并可使用此前真值，误差偏乐观；候选总体误差如下'])
        writer.writerow(['模型', 'alpha', 'MAE', 'WAPE'])
        for c in result.get('comparisons', []):
            writer.writerow([
                c['model'], c['alpha'] if c['alpha'] is not None else '',
                c['mae'], '无实际需求分母' if c['wape'] is None else c['wape'],
            ])
    return stream.getvalue()
