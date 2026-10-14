<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import * as echarts from "echarts";
import { dashboard, listCustomers } from "../api/client";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

const data = ref<any>({});
const customers = ref<any[]>([]);
const chartEl = ref<HTMLDivElement>();
const router = useRouter();
const typeTotal = computed(
  () =>
    Object.values(data.value.type_distribution || {}).reduce(
      (a: number, b: unknown) => a + Number(b),
      0
    ) as number
);
const healthCount = computed(() => {
  const d = data.value.health_distribution || {};
  return { red: d.red || 0, yellow: d.yellow || 0, green: d.green || 0 };
});
const today = computed(() => {
  const d = new Date();
  const wd = ["日", "一", "二", "三", "四", "五", "六"][d.getDay()];
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · 星期${wd}`;
});

onMounted(async () => {
  const [d, c] = await Promise.all([dashboard(), listCustomers()]);
  data.value = d.data;
  customers.value = c.data;
  if (chartEl.value) {
    echarts.init(chartEl.value).setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 16, top: 24, bottom: 28 },
      xAxis: {
        type: "category",
        data: d.data.trend.map((t: any) => t.date.slice(5)),
        axisLine: { lineStyle: { color: "#dfd8c7" } },
        axisLabel: { color: "#6e675c" },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: "#ece6d8" } },
        axisLabel: { color: "#6e675c" },
      },
      series: [
        {
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: 5,
          data: d.data.trend.map((t: any) => t.total),
          lineStyle: { color: "#c15f3c", width: 2 },
          itemStyle: { color: "#c15f3c" },
          areaStyle: { color: "rgba(193, 95, 60, 0.08)" },
        },
      ],
    });
  }
});

function askAi() {
  ElMessage.info("AI 助手对话能力即将上线,入口先行为你留好");
}
</script>

<template>
  <div>
    <!-- 刊头 -->
    <div class="page-head">
      <div class="page-kicker">工作台 · 每日经营速览</div>
      <div style="display:flex; align-items:flex-end; gap:18px">
        <h1 class="page-title" style="margin-bottom:0">今日概览</h1>
        <span class="serif" style="color:var(--ink-3); font-size:15px">{{ today }}</span>
        <span
          v-if="data.last_sync"
          style="margin-left:auto; font-size:12px; color:var(--ink-3)"
        >更新于 {{ data.last_sync.at }}</span>
      </div>
      <div class="page-standfirst">「让每一条客户消息，都变成企业可以理解和经营的业务资产。」</div>
    </div>

    <!-- 01 经营指标 -->
    <section class="section">
      <div class="section-head">
        <span class="section-no">01</span>
        <span class="section-title">经营指标</span>
        <span class="section-note">截至 {{ data.last_sync?.at || "现在" }}</span>
      </div>
      <div class="kpi-row">
        <div class="kpi">
          <div class="k">客户总数</div>
          <div class="v num-serif">{{ data.total_customers ?? 0 }}</div>
          <div class="s">一个群对应一位客户</div>
        </div>
        <div class="kpi">
          <div class="k">已映射 / 待认领会话</div>
          <div class="v num-serif">{{ data.claimed_sessions ?? 0 }} <em>/ {{ data.unclaimed_sessions ?? 0 }}</em></div>
          <div class="s">待认领建议今日完成归属</div>
        </div>
        <div class="kpi">
          <div class="k">今日消息量</div>
          <div class="v num-serif">{{ data.today_messages ?? 0 }}<em v-if="typeTotal"> 条</em></div>
          <div class="s">近 14 天共 {{ typeTotal }} 条</div>
        </div>
        <div class="kpi">
          <div class="k">待处理预警</div>
          <div class="v num-serif warn">{{ data.pending_alert_count ?? 0 }}</div>
          <div class="s"><router-link to="/alerts" class="lnk">进入预警中心 →</router-link></div>
        </div>
      </div>
    </section>

    <!-- 02 趋势 + 03 类型分布 -->
    <section class="section">
      <div class="grid-2">
        <div>
          <div class="section-head" style="margin-top:0">
            <span class="section-no">02</span>
            <span class="section-title">近 14 天消息趋势</span>
            <span class="section-note">共 {{ typeTotal }} 条</span>
          </div>
          <div class="card"><div ref="chartEl" style="height: 250px" /></div>
        </div>
        <div>
          <div class="section-head" style="margin-top:0">
            <span class="section-no">03</span>
            <span class="section-title">消息类型分布</span>
            <span class="section-note">覆盖全部会话</span>
          </div>
          <div class="card">
            <div v-for="(cnt, mt) in data.type_distribution || {}" :key="mt" class="dist-row">
              <span class="dist-k">{{ mt }}</span>
              <div class="dist-bar">
                <i :style="{ width: (typeTotal ? (Number(cnt) / typeTotal) * 100 : 0) + '%' }" />
              </div>
              <span class="dist-v num-serif">
                {{ typeTotal ? Math.round((Number(cnt) / typeTotal) * 100) : 0 }}%
              </span>
            </div>
            <div v-if="!(data.type_distribution && Object.keys(data.type_distribution).length)"
                 style="color:#94a3b8; font-size:13px">暂无数据</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 04 Top5 + 05 待办 / 06 健康度 -->
    <section class="section">
      <div class="grid-2">
        <div>
          <div class="section-head" style="margin-top:0">
            <span class="section-no">04</span>
            <span class="section-title">Top 5 活跃会话</span>
            <span class="section-note">一个会话对应一个客户</span>
          </div>
          <div class="card">
            <el-table :data="data.top_sessions || []" size="small" style="width:100%">
              <el-table-column type="index" label="#" width="44" />
              <el-table-column prop="name" label="会话" min-width="160" />
              <el-table-column label="类型" width="84">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.type === 'group' ? 'warning' : 'info'" effect="plain">
                    {{ row.type === "group" ? "群聊" : "单聊" }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="total" label="消息量" width="90" align="right" />
            </el-table>
          </div>
        </div>
        <div>
          <div class="section-head" style="margin-top:0">
            <span class="section-no">05</span>
            <span class="section-title">待办中心</span>
            <span class="section-note">需要你处理的事项</span>
          </div>
          <div class="card">
            <div class="todo" @click="router.push('/alerts')">
              <span class="t">待处理预警</span><b class="num-serif">{{ data.pending_alert_count ?? 0 }}</b>
            </div>
            <div class="todo" @click="router.push('/customers')">
              <span class="t">待认领会话</span><b class="num-serif">{{ data.unclaimed_sessions ?? 0 }}</b>
            </div>
            <div class="todo" @click="router.push('/insights')">
              <span class="t">洞察分析</span><b>→</b>
            </div>
          </div>

          <div class="section-head" style="margin-top:18px">
            <span class="section-no">06</span>
            <span class="section-title">客户健康度</span>
            <span class="section-note">共 {{ data.total_customers ?? 0 }} 位客户</span>
          </div>
          <div class="card">
            <div class="health-bar">
              <i class="h-red" :style="{ flex: healthCount.red + 1 }" />
              <i class="h-yellow" :style="{ flex: healthCount.yellow + 1 }" />
              <i class="h-green" :style="{ flex: healthCount.green + 1 }" />
            </div>
            <div class="health-legend">
              <span><i class="h-red" /> 红 风险 <b class="num-serif">{{ healthCount.red }}</b></span>
              <span><i class="h-yellow" /> 黄 关注 <b class="num-serif">{{ healthCount.yellow }}</b></span>
              <span><i class="h-green" /> 绿 稳定 <b class="num-serif">{{ healthCount.green }}</b></span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- AI 助手横幅 -->
    <section class="section">
      <div class="ai-band">
        <div>
          <div class="ai-kicker">◆ AI 助手</div>
          <div class="ai-title serif">问问你的 AI 助手</div>
          <div class="ai-sub">用一句话了解客户动向，例如：「近两周哪些客户超过 7 天没有回复？」</div>
        </div>
        <div class="ai-input">
          <input placeholder="输入你的问题，交给 AI 助手" @keydown.enter="askAi" />
          <button @click="askAi">提问</button>
        </div>
      </div>
    </section>

    <!-- 07 采集状态 -->
    <section class="section">
      <div class="section-head">
        <span class="section-no">07</span>
        <span class="section-title">采集状态</span>
        <span class="section-note"><router-link to="/collector" class="lnk">对应「系统 · 采集与通道」→</router-link></span>
      </div>
      <div class="card collect">
        <div>
          <div class="ck">最近同步</div>
          <div class="cv" v-if="data.last_sync">{{ data.last_sync.type }} · {{ data.last_sync.status }}</div>
          <div class="cv" v-else>暂无同步记录</div>
        </div>
        <div>
          <div class="ck">心跳</div>
          <div class="cv">系统正常</div>
        </div>
        <div>
          <div class="ck">数据归属</div>
          <div class="cv">本地私有化存储 · 100% 自有</div>
        </div>
        <div>
          <div class="ck">权限边界</div>
          <div class="cv">永久只收不发，不向客户触发任何消息</div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.kpi { background: var(--paper-card); border: 1px solid var(--rule); border-radius: 4px; padding: 14px 16px; }
.kpi .k { font-size: 12px; color: var(--ink-3); letter-spacing: 0.06em; }
.kpi .v { font-family: var(--serif); font-size: 38px; font-weight: 600; line-height: 1.2; color: var(--ink); }
.kpi .v em { font-style: normal; font-size: 17px; color: var(--ink-3); }
.kpi .v.warn { color: var(--accent-ink); }
.kpi .s { font-size: 12px; color: var(--ink-3); margin-top: 2px; }
.lnk { color: var(--accent-ink); text-decoration: none; }
.lnk:hover { text-decoration: underline; }

.grid-2 { display: grid; grid-template-columns: 3fr 2fr; gap: 22px; align-items: start; }

.dist-row { display: flex; align-items: center; gap: 10px; margin: 9px 0; }
.dist-k { width: 62px; font-size: 12px; color: var(--ink-2); }
.dist-bar { flex: 1; height: 8px; background: var(--paper-deep); border-radius: 2px; overflow: hidden; }
.dist-bar i { display: block; height: 100%; background: var(--accent); }
.dist-v { width: 44px; text-align: right; font-size: 13px; color: var(--ink-2); }

.todo { display: flex; justify-content: space-between; align-items: center;
        padding: 11px 4px; border-bottom: 1px solid var(--rule); cursor: pointer; }
.todo:last-child { border-bottom: none; }
.todo:hover .t { color: var(--accent-ink); }
.todo .t { font-size: 14px; color: var(--ink); }
.todo b { color: var(--accent-ink); font-size: 18px; }

.health-bar { display: flex; height: 10px; border-radius: 3px; overflow: hidden; }
.health-bar i { display: block; }
.h-red { background: #b3402a; }
.h-yellow { background: #c98a2d; }
.h-green { background: #3d7a44; }
.health-legend { display: flex; gap: 18px; margin-top: 12px; font-size: 12px; color: var(--ink-2); }
.health-legend span { display: inline-flex; align-items: center; gap: 6px; }
.health-legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.health-legend b { font-size: 15px; color: var(--ink); }

.ai-band {
  background: var(--paper-deep);
  border: 1px solid var(--rule);
  border-radius: 4px;
  padding: 20px 24px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.ai-kicker { font-size: 12px; letter-spacing: 0.18em; color: var(--accent-ink); }
.ai-title { font-size: 22px; font-weight: 600; margin: 2px 0; color: var(--ink); }
.ai-sub { font-size: 13px; color: var(--ink-2); }
.ai-input { margin-left: auto; display: flex; gap: 8px; flex: none; width: 42%; }
.ai-input input {
  flex: 1;
  background: var(--paper-card);
  border: 1px solid var(--rule);
  border-radius: 3px;
  padding: 9px 12px;
  font-size: 14px;
  color: var(--ink);
  outline: none;
  font-family: var(--sans);
}
.ai-input input:focus { border-color: var(--accent); }
.ai-input button {
  background: var(--ink);
  color: var(--paper);
  border: none;
  border-radius: 3px;
  padding: 0 18px;
  font-size: 14px;
  cursor: pointer;
  font-family: var(--sans);
}
.ai-input button:hover { background: var(--accent-ink); }

.collect { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
.collect .ck { font-size: 12px; color: var(--ink-3); margin-bottom: 3px; }
.collect .cv { font-size: 14px; color: var(--ink); }

@media (max-width: 1100px) {
  .kpi-row, .grid-2, .collect { grid-template-columns: 1fr 1fr; }
}
</style>
