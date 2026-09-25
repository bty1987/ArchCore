<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import * as echarts from "echarts";
import { dashboard } from "../api/client";

const data = ref<any>({});
const chartEl = ref<HTMLDivElement>();
const typeTotal = computed(
  () =>
    Object.values(data.value.type_distribution || {}).reduce(
      (a: number, b: unknown) => a + Number(b),
      0
    ) as number
);

onMounted(async () => {
  const { data: d } = await dashboard();
  data.value = d;
  if (chartEl.value) {
    const chart = echarts.init(chartEl.value);
    chart.setOption({
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: d.trend.map((t: any) => t.date.slice(5)) },
      yAxis: { type: "value" },
      series: [{ type: "line", smooth: true, areaStyle: {}, data: d.trend.map((t: any) => t.total) }],
    });
  }
});
</script>

<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="6"><div class="card stat">
        <div class="k">客户总数</div><div class="v">{{ data.total_customers ?? "-" }}</div></div>
      </el-col>
      <el-col :span="6"><div class="card stat">
        <div class="k">已映射会话</div><div class="v">{{ data.claimed_sessions ?? "-" }}</div></div>
      </el-col>
      <el-col :span="6"><div class="card stat">
        <div class="k">待认领群</div><div class="v">{{ data.unclaimed_sessions ?? "-" }}</div></div>
      </el-col>
      <el-col :span="6"><div class="card stat">
        <div class="k">今日消息量</div><div class="v">{{ data.today_messages ?? "-" }}</div></div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="16">
        <div class="card">
          <h4>近 14 天消息趋势</h4>
          <div ref="chartEl" style="height: 280px" />
        </div>
      </el-col>
      <el-col :span="8">
        <div class="card">
          <h4>待处理预警 TOP（{{ data.pending_alert_count ?? 0 }}）</h4>
          <el-table :data="data.pending_alerts || []" size="small">
            <el-table-column prop="rule_code" label="规则" />
            <el-table-column prop="level" label="级别" width="70" />
            <el-table-column prop="created_at" label="时间" width="90"
                             :formatter="(_: any, __: any, v: string) => (v || '').slice(5, 16)" />
          </el-table>
          <h4 style="margin-top: 16px">采集状态</h4>
          <div v-if="data.last_sync">
            {{ data.last_sync.type }} · {{ data.last_sync.status }} · {{ data.last_sync.at }}
          </div>
          <el-tag v-else type="info">暂无同步记录</el-tag>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat { text-align: center; }
.k { color: #64748b; font-size: 13px; }
.v { font-size: 28px; font-weight: 700; margin-top: 4px; }
</style>
