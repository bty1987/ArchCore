<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import * as echarts from "echarts";
import { listCustomers, customerOverview, listUnclaimed, claimSessions, listAlerts,
         getCustomerSummary, generateCustomerSummary, listSessions, exportSessionCsv } from "../api/client";
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
const summary = ref<any>({});
const summaryDays = ref(7);
const summarizing = ref(false);
const activeTab = ref("overview");
const customerSessions = ref<any[]>([]);
const maxHour = computed(() => Math.max(1, ...(overview.value.active_hours || [])));
const keywordHits = computed(() => overview.value.keyword_hits || []);

onMounted(async () => {
  const customers = await listCustomers();
  customer.value = customers.data.find((c: any) => c.id === cid) || {};
  const ov = await customerOverview(cid);
  overview.value = ov.data;
  alerts.value = (await listAlerts({ customer_id: cid })).data;
  summary.value = (await getCustomerSummary(cid)).data;
  customerSessions.value = (await listSessions({ customer_id: cid })).data;
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

async function genSummary() {
  summarizing.value = true;
  try {
    const r = await generateCustomerSummary(cid, summaryDays.value);
    summary.value = { content: r.data.content, days: r.data.days, created_at: new Date().toISOString() };
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || "生成失败");
  } finally {
    summarizing.value = false;
  }
}

async function exportSession(id: number) {
  const resp = await exportSessionCsv(id);
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `session-${id}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

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
    <div class="page-head">
      <div class="page-kicker">业务 · 客户中心</div>
      <h1 class="page-title" style="font-size:34px">{{ customer.name || "客户档案" }}</h1>
      <div class="page-standfirst">
        <el-link type="primary" @click="router.push('/customers')">← 返回客户列表</el-link>
      </div>
    </div>
    <div class="card">
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
        <div class="card" style="padding: 0">
          <el-tabs v-model="activeTab" style="padding: 4px 14px 14px">
            <el-tab-pane label="分析" name="overview">
              <h4>活跃时段（近 30 天）</h4>
              <div style="display: flex; align-items: flex-end; gap: 2px; height: 80px">
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
              <h4 style="margin-top: 14px">标签汇总</h4>
              <div style="display: flex; flex-wrap: wrap; gap: 6px">
                <el-tag v-for="t in overview.tag_summary || []" :key="t.tag" type="warning">
                  #{{ t.tag }}（{{ t.count }}）
                </el-tag>
                <span v-if="!(overview.tag_summary || []).length"
                      style="color: #94a3b8; font-size: 13px">暂无标注——在消息检索中给消息打标签</span>
              </div>
            </el-tab-pane>

            <el-tab-pane label="会话" name="sessions">
              <el-table :data="customerSessions" size="small">
                <el-table-column label="会话" min-width="140">
                  <template #default="{ row }">{{ row.name || row.wx_id }}</template>
                </el-table-column>
                <el-table-column prop="message_count" label="消息" width="70" />
                <el-table-column label="操作" width="140">
                  <template #default="{ row }">
                    <el-button link type="primary"
                               @click="router.push({ path: '/sessions', query: { session_id: row.id } })">
                      检索
                    </el-button>
                    <el-button link @click="exportSession(row.id)">导出</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>

            <el-tab-pane label="预警" name="alerts">
              <el-timeline style="padding-left: 4px; margin-top: 8px">
                <el-timeline-item v-for="a in alerts" :key="a.id"
                                  :timestamp="String(a.created_at).slice(0, 16)"
                                  :type="a.level === 'red' ? 'danger' : a.level === 'orange' ? 'warning' : 'primary'">
                  {{ a.rule_code }}（{{ a.level }}）
                </el-timeline-item>
              </el-timeline>
              <div v-if="!alerts.length" style="color: #94a3b8; font-size: 13px">暂无预警</div>
            </el-tab-pane>

            <el-tab-pane label="AI 摘要" name="ai">
              <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 10px">
                <el-select v-model="summaryDays" style="width: 110px">
                  <el-option :value="7" label="近 7 天" /><el-option :value="14" label="近 14 天" />
                  <el-option :value="30" label="近 30 天" />
                </el-select>
                <el-button type="primary" :loading="summarizing" @click="genSummary">生成摘要</el-button>
                <span v-if="summary.created_at" style="color:#94a3b8; font-size:12px">
                  {{ String(summary.created_at).slice(0, 16) }}
                </span>
              </div>
              <div v-if="summary.content" style="white-space: pre-wrap; line-height: 1.7">{{ summary.content }}</div>
              <div v-else style="color:#94a3b8; font-size:13px">
                尚未生成。需先在 系统设置→AI 配置 填写 OpenAI 兼容接口。
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-col>
    </el-row>
    <el-row :gutter="16">
      <el-col :span="24">
        <div class="card">
          <h4>AI 摘要（可插拔 OpenAI 兼容接口，需在系统设置配置）</h4>
          <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 10px">
            <el-select v-model="summaryDays" style="width: 110px">
              <el-option :value="7" label="近 7 天" /><el-option :value="14" label="近 14 天" />
              <el-option :value="30" label="近 30 天" />
            </el-select>
            <el-button type="primary" :loading="summarizing" @click="genSummary">生成摘要</el-button>
            <span v-if="summary.created_at" style="color:#94a3b8; font-size:12px">
              生成于 {{ String(summary.created_at).slice(0, 16) }}
            </span>
          </div>
          <div v-if="summary.content" style="white-space: pre-wrap; line-height: 1.7">{{ summary.content }}</div>
          <div v-else style="color:#94a3b8; font-size:13px">尚未生成。需先在 系统设置→AI 配置 填写接口信息。</div>
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
