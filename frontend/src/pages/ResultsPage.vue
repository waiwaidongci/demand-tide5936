<script setup lang="ts">
import { onMounted, ref, computed } from 'vue';
import { useRoute } from 'vue-router';
import { runStore, loadRun } from '../stores/runs';
import { exportRun } from '../api/runs';
import { publish } from '../api/releases';
import { isAdmin } from '../stores/auth';
import { useTask } from '../hooks/useTask';
import { usePolling } from '../hooks/usePolling';
import { modelName, number } from '../utils/format';
import PageHeading from '../components/common/PageHeading.vue';
import ErrorNotice from '../components/common/ErrorNotice.vue';
import StatusBadge from '../components/common/StatusBadge.vue';
import ForecastChart from '../components/ForecastChart.vue';
import type { MultiStepResult } from '../types/domain';

const route = useRoute();
const { error, busy, execute } = useTask();
const note = ref('作为下周日配参考，节假日需求另行复核。');
const published = ref(false);
const expanded = ref<Set<number>>(new Set([1]));
const refresh = () => execute(() => loadRun(Number(route.params.id)));
onMounted(refresh);
usePolling(() => {
  if (['queued', 'running'].includes(runStore.selected?.status || '')) refresh();
});
const release = () => execute(async () => {
  await publish(Number(route.params.id), note.value);
  published.value = true;
});
const exportFile = () => execute(() => exportRun(Number(route.params.id)));

const multi = computed<MultiStepResult | null>(() => {
  const r = runStore.selected?.result;
  return r && (r as MultiStepResult).backtest_mode === 'multi_step' ? r as MultiStepResult : null;
});
const toggle = (i: number) => {
  const next = new Set(expanded.value);
  next.has(i) ? next.delete(i) : next.add(i);
  expanded.value = next;
};
const pct = (w: number | null) => w === null ? '无实际需求分母' : (w * 100).toFixed(2) + '%';
</script>

<template>
  <PageHeading index="04 / FORECAST" :title="runStore.selected?.name || '读取预测档案'"
    subtitle="预测用于计划讨论，结合近期业务变化复核后发布。" />
  <ErrorNotice :message="error" @retry="refresh" />
  <template v-if="runStore.selected">
    <div class="section-heading">
      <h2>{{ runStore.selected.series?.name }}</h2>
      <StatusBadge :status="runStore.selected.status" />
    </div>
    <p v-if="runStore.selected.error" class="error">{{ runStore.selected.error }}
      <RouterLink to="/experiments">调整参数并重建任务 →</RouterLink>
    </p>
    <p v-if="['queued', 'running'].includes(runStore.selected.status)" class="empty">
      后台正在按 {{ runStore.selected.horizon }} 天预测段滚动回测，本页会自动刷新。
    </p>

    <template v-if="runStore.selected.status === 'completed'">
      <!-- 现行口径：滚动多步回测 -->
      <template v-if="multi">
        <div class="result-summary">
          <div>
            <small>入选模型（按总体 MAE 选优）</small>
            <h2>{{ modelName(multi.selected.model) }}<template v-if="multi.selected.alpha !== null"> α={{ multi.selected.alpha }}</template></h2>
          </div>
          <div>
            <small>总体 MAE / WAPE</small>
            <h2>{{ number(multi.selected.mae) }} 束 · {{ pct(multi.selected.wape) }}</h2>
          </div>
          <div>
            <small>回测段 × 段长</small>
            <h2>{{ multi.segment_count }} 段 × {{ multi.horizon }} 天</h2>
          </div>
          <div>
            <small>观测 / 回测覆盖</small>
            <h2>{{ multi.training_days }} / {{ multi.validation_days }} 天</h2>
          </div>
        </div>

        <ForecastChart :points="runStore.selected.points" />
        <p class="method-note">{{ multi.interval_note }}</p>

        <div class="section-heading">
          <h2>候选总体误差 / 相同起点与完整预测段</h2>
          <span>每个起点仅用此前观测，一次推出 {{ multi.horizon }} 天，段内不以真值纠偏</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr><th>模型</th><th>α</th><th>总体 MAE / 束</th><th>总体 WAPE</th><th>选优</th></tr>
            </thead>
            <tbody>
              <tr v-for="m in multi.comparisons" :key="m.model + String(m.alpha)">
                <td>{{ modelName(m.model) }}</td>
                <td>{{ m.alpha ?? '—' }}</td>
                <td>{{ number(m.mae) }}</td>
                <td>{{ pct(m.wape) }}</td>
                <td>
                  <span v-if="m.model === multi.selected.model && m.alpha === multi.selected.alpha" class="badge completed">入选</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="section-heading"><h2>分提前天数误差（入选模型）</h2><span>提前 1 天 = 备货首日，样本均为 {{ multi.segment_count }} 段</span></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>提前天数</th><th>MAE / 束</th><th>WAPE</th><th>样本段数</th></tr></thead>
            <tbody>
              <tr v-for="m in multi.lead_metrics" :key="m.lead_day">
                <td>第 {{ m.lead_day }} 天</td>
                <td>{{ number(m.mae) }}</td>
                <td>{{ pct(m.wape) }}</td>
                <td>{{ m.samples }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="section-heading">
          <h2>回测分段核对 / 预测与真值</h2>
          <span>段互不重叠、末端对齐；点击展开每段逐日明细</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>回测段</th><th>起点（此前观测天数）</th><th>覆盖下标</th><th>段 MAE</th><th>段 WAPE</th><th></th></tr></thead>
            <tbody v-for="(seg, i) in multi.backtest_segments" :key="i">
              <tr>
                <td><strong>第 {{ i + 1 }} 段</strong></td>
                <td>{{ seg.origin_index }} 天</td>
                <td>{{ seg.start_index }} – {{ seg.end_index - 1 }}</td>
                <td>{{ number(seg.segment_mae) }}</td>
                <td>{{ pct(seg.segment_wape) }}</td>
                <td><a href="#" @click.prevent="toggle(i + 1)">{{ expanded.has(i + 1) ? '收起 ↑' : '展开逐日核对 ↓' }}</a></td>
              </tr>
              <tr v-if="expanded.has(i + 1)">
                <td colspan="6" style="padding:0">
                  <table style="margin:0">
                    <thead><tr><th>提前天数</th><th>真值</th><th>预测</th><th>误差（真值-预测）</th><th>绝对误差</th></tr></thead>
                    <tbody>
                      <tr v-for="row in seg.predictions" :key="row.lead_day">
                        <td>第 {{ row.lead_day }} 天</td>
                        <td>{{ number(row.actual) }}</td>
                        <td>{{ number(row.predicted) }}</td>
                        <td :style="{ color: row.error < 0 ? 'oklch(46% .15 30)' : 'oklch(42% .075 145)' }">{{ number(row.error) }}</td>
                        <td>{{ number(row.abs_error) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <!-- 旧口径：历史任务的逐日一步回测 -->
      <template v-else-if="runStore.selected.result">
        <div class="result-summary">
          <div>
            <small>入选模型（旧版一步回测）</small>
            <h2>{{ modelName(runStore.selected.result.selected.model) }}</h2>
          </div>
          <div>
            <small>回测 MAE</small>
            <h2>{{ number(runStore.selected.result.selected.mae) }} 束</h2>
          </div>
          <div>
            <small>训练 / 验证</small>
            <h2>{{ runStore.selected.result.training_days }} / {{ runStore.selected.result.validation_days }} 天</h2>
          </div>
        </div>
        <ForecastChart :points="runStore.selected.points" />
        <p class="method-note">{{ runStore.selected.result.interval_note }}</p>
        <p class="empty" style="margin:12px 0">
          该任务创建于口径升级前，保留原“逐日一步回测”结果：每步只预测次日且可使用此前全部真值，
          未模拟一次备货多天的递推误差，误差偏乐观。重建任务即可得到滚动多步回测与分段核对。
        </p>
        <h2>模型比较 / 滚动一步预测（原口径）</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>模型</th><th>α</th><th>MAE / 束</th><th>WAPE</th></tr></thead>
            <tbody>
              <tr v-for="m in runStore.selected.result.comparisons" :key="m.model + String(m.alpha)">
                <td>{{ modelName(m.model) }}</td>
                <td>{{ m.alpha ?? '—' }}</td>
                <td>{{ number(m.mae) }}</td>
                <td>{{ pct(m.wape) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <div class="section-heading">
        <h2>未来 {{ runStore.selected.horizon }} 天的日配参考</h2>
        <button @click="exportFile">下载预测与回测明细 CSV ↓</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>日期</th><th>点预测</th><th>经验下界</th><th>经验上界</th></tr></thead>
          <tbody>
            <tr v-for="p in runStore.selected.points" :key="p.day">
              <td>{{ p.day }}</td>
              <td>{{ number(p.predicted) }}</td>
              <td>{{ number(p.lower) }}</td>
              <td>{{ number(p.upper) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <form v-if="isAdmin" class="inline-form" @submit.prevent="release">
        <label class="grow">发布说明<input v-model="note" minlength="3" maxlength="500" required /></label>
        <button class="primary" :disabled="busy || published">{{ published ? '已发布到档案' : '发布日配参考 →' }}</button>
      </form>
    </template>
  </template>
</template>
