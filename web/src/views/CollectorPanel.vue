<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ingestHealth, listAuditLogs, listSessions,
  getWhitelist, setAllowAll, addWhitelistRule, deleteWhitelistRule,
} from "../api/client";
import { ElMessage } from "element-plus";

const health = ref<any>({});
const logs = ref<any[]>([]);
const sessions = ref<any[]>([]);
const rules = ref<any[]>([]);
const allowAll = ref(false);
const manual = ref({ wx_id: "", stype: "group", name: "", note: "" });
const search = ref("");

const ruleByWxId = computed(() => {
  const map: Record<string, any> = {};
  for (const r of rules.value) map[r.wx_id] = r;
  return map;
});
const shownSessions = computed(() => {
  const kw = search.value.trim();
  return kw ? sessions.value.filter((s) => (s.name + s.wx_id).includes(kw)) : sessions.value;
});

async function load() {
  health.value = (await ingestHealth()).data;
  logs.value = (await listAuditLogs({ limit: 30 })).data;
  sessions.value = (await listSessions()).data;
  const wl = (await getWhitelist()).data;
  rules.value = wl.rules;
  allowAll.value = wl.allow_all;
}
onMounted(load);

async function toggleAllowAll(v: boolean) {
  await setAllowAll(v);
  ElMessage.success(v ? "已放开白名单（采集全部）" : "已恢复白名单管控");
  load();
}

async function addRule(session: any) {
  await addWhitelistRule({
    wx_id: session.wx_id, stype: session.type,
    name: session.name || session.wx_id,
  });
  ElMessage.success(`已加入白名单：${session.name || session.wx_id}`);
  load();
}

async function removeRule(session: any) {
  const rule = ruleByWxId.value[session.wx_id];
  if (!rule) return;
  await deleteWhitelistRule(rule.id);
  ElMessage.success("已移出白名单");
  load();
}

async function addManual() {
  if (!manual.value.wx_id) return;
  await addWhitelistRule(manual.value);
  manual.value = { wx_id: "", stype: "group", name: "", note: "" };
  ElMessage.success("已添加");
  load();
}

function inWhitelist(wxId: string) {
  return !!ruleByWxId.value[wxId];
}
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
      <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 12px">
        <h4 style="margin: 0">会话白名单</h4>
        <el-switch v-model="allowAll" active-text="采集全部（allow_all，个人测试用）"
                   @change="toggleAllowAll" />
        <div style="flex: 1" />
        <el-input v-model="search" placeholder="搜索会话" style="width: 180px" clearable />
      </div>

      <el-alert v-if="allowAll" type="warning" :closable="false" style="margin-bottom: 10px"
                title="allow_all 已开启：忽略白名单采集全部会话。仅限个人本机测试环境，商用部署禁止。" />

      <el-form inline style="margin-bottom: 10px">
        <el-form-item>
          <el-input v-model="manual.wx_id" placeholder="会话 wx_id" style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-select v-model="manual.stype" style="width: 100px">
            <el-option label="群聊" value="group" /><el-option label="单聊" value="dm" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input v-model="manual.name" placeholder="备注名（可选）" style="width: 160px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="addManual">手动添加</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="shownSessions" size="small" max-height="420">
        <el-table-column label="会话" min-width="180">
          <template #default="{ row }">{{ row.name || row.wx_id }}</template>
        </el-table-column>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'group' ? 'warning' : 'info'">
              {{ row.type === "group" ? "群聊" : "单聊" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message_count" label="已归档消息" width="110" />
        <el-table-column prop="last_msg_at" label="最近消息" width="160" />
        <el-table-column label="白名单" width="120">
          <template #default="{ row }">
            <el-tag v-if="inWhitelist(row.wx_id)" type="success" size="small">采集中</el-tag>
            <el-tag v-else type="info" size="small">未加入</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button v-if="!inWhitelist(row.wx_id)" link type="primary"
                       @click="addRule(row)">加入</el-button>
            <el-button v-else link type="danger" @click="removeRule(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p style="color: #94a3b8; font-size: 12px; margin-top: 8px">
        白名单保存在服务端，采集端每轮同步前自动拉取；修改后下一个采集周期生效。
        未入库的会话（如新配置的群）需等微信同步消息后才会出现消息量。
      </p>
    </div>

    <div class="card">
      <h4>最近操作日志（审计）</h4>
      <el-table :data="logs" size="small">
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
