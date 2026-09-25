<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import { listCustomers, customerOverview, listUnclaimed, claimSessions, listAlerts } from "../api/client";
import { ElMessage } from "element-plus";

const route = useRoute();
const router = useRouter();
const cid = Number(route.params.id);
const customer = ref<any>({});
const overview = ref<any>({});
const unclaimed = ref<any[]>([]);
const selected = ref<number[]>([]);
const chartEl = ref<HTMLDivElement>();
const alerts = ref<any[]>([]);
const maxHour = computed(() => Math.max(1, ...(overview.value.active_hours || [])));
const keywordHits = computed(() => overview.value.keyword_hits || []);

onMounted(async () => {
  const customers = await listCustomers();
  customer.value = customers.data.find((c: any) => c.id === cid) || {};
  const ov = await customerOverview(cid);
  overview.value = ov.data;
  alerts.value = (await listAlerts({ customer_id: cid })).data;
  const un = await listUnclaimed();
  unclaimed.value = un.data;
  if (chartEl.value) {
    echarts.init(chartEl.value).setOption({
      tooltip: { trigger: "axis" },
      legend: { data: ["全部", "客户方"] },
      xAxis: { type: "category", data: ov.data.trend.map((t: any) => t.date.slice(5)) },
      yAxis: { type: "value" },
      series: [
        { name: "全部", type: "bar", data: ov.data.trend.map((t: any) => t.total) },
        { name: "客户方", type: "bar", data: ov.data.trend.map((t: any) => t.external) },
      ],
    });
  }
});

async function claim() {
  if (!selected.value.length) return;
  await claimSessions(cid, selected.value);
  ElMessage.success(`已认领 ${selected.value.length} 个会话`);
  selected.value = [];
  const ov = await customerOverview(cid);
  overview.value = ov.data;
}
</script>

<template>
  <div>
    <div class="card">
      <el-page-header :title="'客户列表'" @back="router.push('/customers')">
        <template #content><b style="font-size: 18px">{{ customer.name }}</b></template>
      </el-page-header>
      <el-descriptions :column="4" style="margin-top: 12px">
        <el-descriptions-item label="行业">{{ customer.industry || "-" }}</el-descriptions-item>
        <el-descriptions-item label="阶段">{{ customer.stage }}</el-descriptions-item>
        <el-descriptions-item label="会话数">{{ overview.session_count ?? "-" }}</el-descriptions-item>
        <el-descriptions-item label="响应 P50">
          {{ overview.response?.p50_minutes ?? "-" }} 分钟
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <el-row :gutter="16">
      <el-col :span="14">
        <div class="card"><h4>30 天活跃趋势</h4>
          <div ref="chartEl" style="height: 260px" /></div>
      </el-col>
      <el-col :span="10">
        <div class="card">
          <h4>活跃时段（近 30 天）</h4>
          <div style="display: flex; align-items: flex-end; gap: 2px; height: 90px">
            <div v-for="(cnt, h) in overview.active_hours || []" :key="h"
                 style="flex: 1; background: #60a5fa; border-radius: 3px 3px 0 0"
                 :title="h + '时：' + cnt + ' 条'"
                 :style="{ height: Math.round((cnt / maxHour) * 100) + '%', minHeight: '3px',
                           opacity: cnt ? 1 : 0.25 }" />
          </div>
          <div style="display: flex; justify-content: space-between; color: #94a3b8; font-size: 11px">
            <span>0</span><span>6</span><span>12</span><span>18</span><span>23</span>
          </div>
          <h4 style="margin-top: 14px">消息类型分布</h4>
          <div style="display: flex; flex-wrap: wrap; gap: 8px">
            <el-tag v-for="(cnt, mt) in overview.type_distribution || {}" :key="mt">
              {{ mt }}：{{ cnt }}
            </el-tag>
            <span v-if="!Object.keys(overview.type_distribution || {}).length"
                  style="color: #94a3b8; font-size: 13px">暂无数据</span>
          </div>
          <h4 style="margin-top: 14px">关键词命中（30 天）</h4>
          <el-table :data="keywordHits" size="small" v-if="keywordHits.length">
            <el-table-column prop="word" label="词条" />
            <el-table-column prop="category" label="类别" width="80" />
            <el-table-column prop="count" label="命中" width="70" />
          </el-table>
          <div v-else style="color: #94a3b8; font-size: 13px">暂无命中</div>
          <h4 style="margin-top: 14px">预警时间线</h4>
          <el-timeline style="padding-left: 4px">
            <el-timeline-item v-for="a in alerts.slice(0, 6)" :key="a.id"
                              :timestamp="String(a.created_at).slice(0, 16)"
                              :type="a.level === 'red' ? 'danger' : a.level === 'orange' ? 'warning' : 'primary'">
              {{ a.rule_code }}（{{ a.level }}）
            </el-timeline-item>
          </el-timeline>
          <div v-if="!alerts.length" style="color: #94a3b8; font-size: 13px">暂无预警</div>
        </div>
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :span="24">
        <div class="card">
          <h4>待认领会话（可归入该客户）</h4>
          <el-select v-model="selected" multiple placeholder="选择待认领群" style="width: 100%">
            <el-option v-for="s in unclaimed" :key="s.id" :label="s.name || s.wx_id" :value="s.id" />
          </el-select>
          <el-button type="primary" style="margin-top: 10px" @click="claim">认领</el-button>
        </div>
      </el-col>
    </el-row>
  </div>
</template>
