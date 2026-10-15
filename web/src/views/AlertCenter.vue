<script setup lang="ts">
import { onMounted, ref } from "vue";
import { listAlerts, handleAlert, listAlertRules, updateAlertRule } from "../api/client";
import { ElMessage } from "element-plus";

const activeTab = ref("pending");
const rows = ref<any[]>([]);
const rules = ref<any[]>([]);
const LEVEL: Record<string, string> = { red: "danger", orange: "warning", yellow: "", gray: "info" };

async function load() {
  rows.value = (await listAlerts({ status: activeTab.value })).data;
  rules.value = (await listAlertRules()).data;
}
onMounted(load);

async function handle(id: number, action: string) {
  const note = action === "ignored" ? "误报忽略" : "已处理";
  await handleAlert(id, action, note);
  ElMessage.success(action === "ignored" ? "已忽略" : "已处理");
  load();
}

async function toggleRule(rule: any) {
  await updateAlertRule(rule.code, rule);
  ElMessage.success("规则已更新");
}
</script>

<template>
  <div>
    <div class="page-head">
      <div class="page-kicker">业务 · 预警中心</div>
      <h1 class="page-title">预警中心</h1>
      <div class="page-standfirst">投诉、超时、沉默、风险词——需要你处理的事，都在这里。</div>
    </div>

    <section class="section">
      <div class="section-head" style="margin-top:0">
        <span class="section-no">01</span>
        <span class="section-title">预警队列</span>
        <span class="section-note">处理与忽略均记录处理人与备注</span>
      </div>
      <div class="card">
    <el-tabs v-model="activeTab" @tab-change="load">
      <el-tab-pane label="待处理" name="pending" />
      <el-tab-pane label="已处理" name="handled" />
      <el-tab-pane label="已忽略" name="ignored" />
    </el-tabs>

    <el-table :data="rows" v-if="activeTab !== 'rules'">
      <el-table-column label="级别" width="80">
        <template #default="{ row }">
          <el-tag :type="LEVEL[row.level] || 'info'">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="rule_code" label="规则" width="150" />
      <el-table-column label="详情" min-width="220">
        <template #default="{ row }">{{ JSON.stringify(row.detail) }}</template>
      </el-table-column>
      <el-table-column prop="created_at" label="触发时间" width="160" />
      <el-table-column label="操作" width="150" v-if="activeTab === 'pending'">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="handle(row.id, 'handled')">处理</el-button>
          <el-button size="small" @click="handle(row.id, 'ignored')">忽略</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="handle_note" label="处理备注" v-else />
    </el-table>

      </div>
    </section>

    <section class="section">
      <div class="section-head" style="margin-top:0">
        <span class="section-no">02</span>
        <span class="section-title">预警规则</span>
        <span class="section-note">启用/停用与冷却时间</span>
      </div>
      <div class="card">
        <el-table :data="rules" size="small">
          <el-table-column prop="code" label="规则" width="150" />
          <el-table-column prop="level" label="级别" width="80" />
          <el-table-column prop="cooldown_minutes" label="冷却(分钟)" width="110" />
          <el-table-column label="启用">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" @change="toggleRule(row)" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>
  </div>
</template>
