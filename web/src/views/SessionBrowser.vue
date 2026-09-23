<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { listSessions, searchMessages, messageContext } from "../api/client";

const sessions = ref<any[]>([]);
const sessionId = ref<number | null>(null);
const q = ref("");
const senderType = ref("");
const items = ref<any[]>([]);
const nextCursor = ref<string | null>(null);
const contextMsg = ref<any[] | null>(null);
const SENDER_LABEL: Record<string, string> = {
  external: "客户方", internal: "我方同事", me: "我", system: "系统",
};

onMounted(async () => {
  const { data } = await listSessions();
  sessions.value = data;
});

watch([sessionId, senderType], load, { deep: true });

async function load(append = false) {
  const params: Record<string, unknown> = { limit: 50 };
  if (sessionId.value) params.session_id = sessionId.value;
  if (q.value) params.q = q.value;
  if (senderType.value) params.sender_type = senderType.value;
  if (append && nextCursor.value) params.cursor = nextCursor.value;
  const { data } = await searchMessages(params);
  items.value = append ? [...items.value, ...data.items] : data.items;
  nextCursor.value = data.next_cursor;
}

async function showContext(row: any) {
  contextMsg.value = (await messageContext(row.id, 10, 10)).data;
}
</script>

<template>
  <div>
    <div class="card" style="display: flex; gap: 12px">
      <el-select v-model="sessionId" placeholder="全部会话" style="width: 240px" filterable clearable>
        <el-option v-for="s in sessions" :key="s.id" :label="s.name || s.wx_id" :value="s.id" />
      </el-select>
      <el-input v-model="q" placeholder="关键词检索（≥3 字全文检索，2 字模糊）"
                style="flex: 1" clearable @change="load()" />
      <el-select v-model="senderType" placeholder="方向" style="width: 120px" clearable>
        <el-option v-for="(label, key) in SENDER_LABEL" :key="key" :label="label" :value="key" />
      </el-select>
      <el-button type="primary" @click="load()">检索</el-button>
    </div>

    <div class="card flow">
      <div v-for="m in items" :key="m.id" class="msg" :class="m.sender_type" @click="showContext(m)">
        <div class="meta">
          {{ new Date(m.ts).toLocaleString() }} · {{ SENDER_LABEL[m.sender_type] || m.sender_type }}
          <el-tag v-if="m.recalled" size="small" type="info">已撤回</el-tag>
        </div>
        <div class="content">{{ m.content }}</div>
      </div>
      <el-empty v-if="!items.length" description="无消息（调整会话/关键词）" />
      <div style="text-align: center; margin-top: 8px" v-if="nextCursor">
        <el-button @click="load(true)">加载更多</el-button>
      </div>
    </div>

    <el-drawer v-model="contextMsg" title="消息上下文" size="45%">
      <div v-for="m in contextMsg || []" :key="m.id" class="msg" :class="m.sender_type">
        <div class="meta">{{ new Date(m.ts).toLocaleString() }} ·
          {{ SENDER_LABEL[m.sender_type] || m.sender_type }}</div>
        <div class="content">{{ m.content }}</div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.flow { max-height: calc(100vh - 220px); overflow: auto; }
.msg { padding: 8px 12px; border-radius: 10px; margin: 6px 0; cursor: pointer; }
.msg.external { background: #fff; border: 1px solid #e2e8f0; }
.msg.internal, .msg.me { background: #e0f2fe; margin-left: 15%; }
.msg.system { background: transparent; color: #94a3b8; font-size: 12px; text-align: center; }
.msg:hover { box-shadow: 0 1px 6px rgba(0,0,0,.1); }
.meta { font-size: 11px; color: #94a3b8; }
.content { margin-top: 2px; white-space: pre-wrap; }
</style>
