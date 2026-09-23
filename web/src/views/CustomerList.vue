<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { listCustomers, createCustomer, exportCustomerCsv } from "../api/client";
import { ElMessage } from "element-plus";

const router = useRouter();
const rows = ref<any[]>([]);
const q = ref("");
const stage = ref("");
const dialog = ref(false);
const form = ref({ name: "", industry: "", stage: "contact", owner_user_id: null });

const STAGES = [
  { value: "contact", label: "接触" }, { value: "solution", label: "方案" },
  { value: "quote", label: "报价" }, { value: "won", label: "成交" },
  { value: "service", label: "售后" },
];

async function load() {
  const { data } = await listCustomers({ q: q.value || undefined, stage: stage.value || undefined });
  rows.value = data;
}
onMounted(load);

async function save() {
  await createCustomer(form.value);
  dialog.value = false;
  form.value = { name: "", industry: "", stage: "contact", owner_user_id: null };
  ElMessage.success("已创建");
  load();
}

async function doExport(id: number) {
  const resp = await exportCustomerCsv(id);
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `customer-${id}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="card">
    <div style="display: flex; gap: 12px; margin-bottom: 12px">
      <el-input v-model="q" placeholder="搜索客户名" style="width: 220px" clearable @change="load" />
      <el-select v-model="stage" placeholder="阶段" style="width: 140px" clearable @change="load">
        <el-option v-for="s in STAGES" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <div style="flex: 1" />
      <el-button type="primary" @click="dialog = true">新建客户</el-button>
    </div>

    <el-table :data="rows" @row-click="(r: any) => router.push(`/customers/${r.id}`)">
      <el-table-column prop="name" label="客户" min-width="140" />
      <el-table-column prop="industry" label="行业" width="110" />
      <el-table-column label="阶段" width="90">
        <template #default="{ row }">
          {{ STAGES.find((s) => s.value === row.stage)?.label || row.stage }}
        </template>
      </el-table-column>
      <el-table-column label="健康度" width="110">
        <template #default="{ row }">
          <el-tag v-if="row.health_level" :type="row.health_level === 'green' ? 'success' :
            row.health_level === 'yellow' ? 'warning' : 'danger'">
            {{ row.health_score }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="session_count" label="会话数" width="80" />
      <el-table-column prop="last_msg_at" label="最近消息" width="160" />
      <el-table-column label="操作" width="90">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="doExport(row.id)">导出</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新建客户" width="420">
      <el-form label-width="64">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="form.industry" /></el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="form.stage">
            <el-option v-for="s in STAGES" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
