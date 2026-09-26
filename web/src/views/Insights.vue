<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import * as echarts from "echarts";
import { getInsights } from "../api/client";
import { useRouter } from "vue-router";

const data = ref<any>({});
const healthEl = ref<HTMLDivElement>();
const rankEl = ref<HTMLDivElement>();
const router = useRouter();
const typeTotal = computed(() => {
  const d = data.value.type_distribution || {};
  return Object.values(d).reduce((a: number, b: unknown) => a + Number(b), 0) as number;
});

onMounted(async () => {
  const { data: d } = await getInsights();
  data.value = d;
  if (healthEl.value) {
    const hd = d.health_distribution || {};
    echarts.init(healthEl.value).setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "pie", radius: ["42%", "68%"],
        data: [
          { name: "红（危险）", value: hd.red || 0, itemStyle: { color: "#ef4444" } },
          { name: "黄（关注）", value: hd.yellow || 0, itemStyle: { color: "#f59e0b" } },
          { name: "绿（健康）", value: hd.green || 0, itemStyle: { color: "#22c55e" } },
        ],
        label: { formatter: "{b}\n{c}" },
      }],
    });
  }
  if (rankEl.value) {
    const sorted = [...(d.customer_rank || [])].sort((a, b) => a.total - b.total);
    echarts.init(rankEl.value).setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 90, right: 30, top: 10, bottom: 24 },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: sorted.map((c: any) => c.name) },
      series: [{ type: "bar", data: sorted.map((c: any) => c.total), color: "#60a5fa",
                 barMaxWidth: 18 }],
    });
  }
});
</script>

<template>
  <div>
    <el-row :gutter="16">
      <el-col :span="8">
        <div class="card">
          <h4>客户健康度分布</h4>
          <div ref="healthEl" style="height: 240px" />
        </div>
        <div class="card">
          <h4>消息类型结构（全库）</h4>
          <div v-for="(cnt, mt) in data.type_distribution || {}" :key="mt"
               style="display:flex; align-items:center; gap:8px; margin:5px 0">
            <el-tag size="small" style="width:70px; text-align:center">{{ mt }}</el-tag>
            <el-progress :percentage="Math.round((cnt / typeTotal) * 100)" :show-text="false"
                         style="flex:1" />
            <span style="width:70px; text-align:right; font-size:12px; color:#64748b">{{ cnt }}</span>
          </div>
          <div v-if="!(data.type_distribution && Object.keys(data.type_distribution).length)"
               style="color:#94a3b8; font-size:13px">暂无数据</div>
        </div>
      </el-col>
      <el-col :span="10">
        <div class="card">
          <h4>客户消息量排行（Top 10）</h4>
          <div ref="rankEl" style="height: 280px" />
          <el-table :data="data.customer_rank || []" size="small" style="margin-top: 10px">
            <el-table-column label="客户" min-width="120">
              <template #default="{ row }">
                <el-link type="primary" @click="router.push(`/customers/${row.customer_id}`)">
                  {{ row.name }}
                </el-link>
              </template>
            </el-table-column>
            <el-table-column label="健康度" width="90">
              <template #default="{ row }">{{ row.health_score ?? "-" }}</template>
            </el-table-column>
            <el-table-column prop="p50" label="响应 P50(分)" width="110" />
            <el-table-column prop="total" label="消息量" width="80" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="card">
          <h4>词库命中排行（全库）</h4>
          <el-table :data="data.keyword_hits || []" size="small">
            <el-table-column prop="word" label="词条" />
            <el-table-column prop="category" label="类别" width="80" />
            <el-table-column prop="count" label="命中" width="70" />
          </el-table>
          <div v-if="!(data.keyword_hits || []).length" style="color:#94a3b8; font-size:13px">
            暂无命中——词库可在系统设置中维护
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

