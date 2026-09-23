<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import { listCustomers, customerOverview, listUnclaimed, claimSessions } from "../api/client";
import { ElMessage } from "element-plus";

const route = useRoute();
const router = useRouter();
const cid = Number(route.params.id);
const customer = ref<any>({});
const overview = ref<any>({});
const unclaimed = ref<any[]>([]);
const selected = ref<number[]>([]);
const chartEl = ref<HTMLDivElement>();

onMounted(async () => {
  const customers = await listCustomers();
  customer.value = customers.data.find((c: any) => c.id === cid) || {};
  const ov = await customerOverview(cid);
  overview.value = ov.data;
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
