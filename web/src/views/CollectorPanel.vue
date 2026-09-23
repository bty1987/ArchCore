<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ingestHealth, listAuditLogs } from "../api/client";

const health = ref<any>({});
const tasks = ref<any[]>([]);

onMounted(async () => {
  health.value = (await ingestHealth()).data;
  tasks.value = (await listAuditLogs({ limit: 30 })).data;
});
</script>

<template>
  <div>
    <div class="card">
      <h4>采集状态</h4>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="最近同步类型">{{ health.last_sync?.type || "-" }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="health.last_sync?.status === 'success' ? 'success' : 'danger'">
            {{ health.last_sync?.status || "unknown" }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="同步时间">{{ health.last_sync?.at || "-" }}</el-descriptions-item>
        <el-descriptions-item label="已归档消息数">{{ health.message_count ?? "-" }}</el-descriptions-item>
        <el-descriptions-item label="版本冻结" :span="2">
          微信 3.9.12（32 位）+ 采集工具版本组合已在部署时登记；只评估不升级
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <div class="card">
      <h4>最近操作日志（审计）</h4>
      <el-table :data="tasks" size="small">
        <el-table-column prop="id" label="#" width="70" />
        <el-table-column prop="action" label="动作" width="140" />
        <el-table-column prop="target" label="对象" width="180" />
        <el-table-column label="明细" min-width="220">
          <template #default="{ row }">{{ JSON.stringify(row.detail) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="160" />
      </el-table>
    </div>
  </div>
</template>
