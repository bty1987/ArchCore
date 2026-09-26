<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import * as echarts from "echarts";
import { dashboard, listCustomers } from "../api/client";
import { useRouter } from "vue-router";

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

onMounted(async () => {
  const [d, c] = await Promise.all([dashboard(), listCustomers()]);
  data.value = d.data;
  customers.value = c.data;
  if (chartEl.value) {
    echarts.init(chartEl.value).setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 40, right: 16, top: 24, bottom: 28 },
      xAxis: { type: "category", data: d.data.trend.map((t: any) => t.date.slice(5)) },
      yAxis: { type: "value" },
      series: [
        { type: "line", smooth: true, areaStyle: { opacity: 0.15 },
          data: d.data.trend.map((t: any) => t.total), color: "#60a5fa" },
      ],
    });
  }
});
</script>

<template>
  <div>
    <!-- 顶部四指标 -->
    <el-row :gutter="16">
      <el-col :span="6"><div class="card stat">
        <div class="k">客户总数</div><div class="v">{{ data.total_customers ?? 0 }}</div></div>
      </el-col>
      <el-col :span="6"><div class="card stat">
        <div class="k">已映射 / 待认领会话</div>
        <div class="v">{{ data.claimed_sessions ?? 0 }} <span class="v-sub">/ {{ data.unclaimed_sessions ?? 0 }}</span></div></div>
      </el-col>
      <el-col :span="6"><div class="card stat">
        <div class="k">今日消息量</div><div class="v">{{ data.today_messages ?? 0 }}</div></div>
      </el-col>
      <el-col :span="6"><div class="card stat">
        <div class="k">待处理预警</div>
        <div class="v warn">{{ data.pending_alert_count ?? 0 }}</div></div>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="16">
        <div class="card">
          <h4>近 14 天消息趋势</h4>
          <div ref="chartEl" style="height: 250px" />
        </div>
        <div class="card">
          <h4>Top 5 活跃会话</h4>
          <el-table :data="data.top_sessions || []" size="small">
            <el-table-column prop="name" label="会话" min-width="160" />
            <el-table-column label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.type === 'group' ? 'warning' : 'info'">
                  {{ row.type === "group" ? "群聊" : "单聊" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="total" label="消息量" width="90" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="8">
        <div class="card">
          <h4>待办中心</h4>
          <div class="todo" @click="router.push('/alerts')">
            <span>🔔 待处理预警</span><b>{{ data.pending_alert_count ?? 0 }}</b>
          </div>
          <div class="todo" @click="router.push('/customers')">
            <span>📥 待认领会话</span><b>{{ data.unclaimed_sessions ?? 0 }}</b>
          </div>
          <div class="todo" @click="router.push('/insights')">
            <span>📈 洞察分析</span><b>→</b>
          </div>
          <h4 style="margin-top: 14px">客户健康度</h4>
          <div style="display:flex; gap:10px">
            <el-tag type="danger">红 {{ healthCount.red }}</el-tag>
            <el-tag type="warning">黄 {{ healthCount.yellow }}</el-tag>
            <el-tag type="success">绿 {{ healthCount.green }}</el-tag>
          </div>
          <h4 style="margin-top: 14px">采集状态</h4>
          <div v-if="data.last_sync" style="font-size:13px; color:#475569">
            {{ data.last_sync.type }} · {{ data.last_sync.status }} · {{ data.last_sync.at }}
          </div>
          <el-tag v-else type="info">暂无同步记录</el-tag>
        </div>
        <div class="card">
          <h4>消息类型分布</h4>
          <div v-for="(cnt, mt) in data.type_distribution || {}" :key="mt"
               style="display:flex; align-items:center; gap:8px; margin:4px 0">
            <el-tag size="small" style="width:64px; text-align:center">{{ mt }}</el-tag>
            <el-progress :percentage="typeTotal ? Math.round((cnt / typeTotal) * 100) : 0"
                         :show-text="false" style="flex:1" />
            <span style="width:60px; text-align:right; font-size:12px; color:#64748b">{{ cnt }}</span>
          </div>
          <div v-if="!(data.type_distribution && Object.keys(data.type_distribution).length)"
               style="color:#94a3b8; font-size:13px">暂无数据</div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.stat { text-align: center; }
.k { color: #64748b; font-size: 13px; }
.v { font-size: 26px; font-weight: 700; margin-top: 4px; }
.v-sub { font-size: 15px; color: #94a3b8; font-weight: 400; }
.warn { color: #f59e0b; }
.todo { display: flex; justify-content: space-between; align-items: center;
        padding: 10px 12px; background: #f8fafc; border-radius: 8px; margin: 6px 0;
        cursor: pointer; }
.todo:hover { background: #eef2ff; }
</style>
