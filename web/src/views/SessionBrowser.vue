<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { listSessions, searchMessages, messageContext, exportSessionCsv,
         addMessageTag, deleteMessageTag, listCustomers } from "../api/client";

const route = useRoute();

const sessions = ref<any[]>([]);
const sessionId = ref<number | null>(null);
const q = ref("");
const senderType = ref("");
const items = ref<any[]>([]);
const nextCursor = ref<string | null>(null);
const contextMsg = ref<any[] | null>(null);
const dateRange = ref<[string, string] | null>(null);
const senderWxid = ref("");
const customerId = ref<number | null>(null);
const customers = ref<any[]>([]);
const tagDialog = ref(false);
const tagMsg = ref<any>(null);
const tagInput = ref("");
const SENDER_LABEL: Record<string, string> = {
  external: "客户方", internal: "我方同事", me: "我", system: "系统",
};
const TYPE_LABEL: Record<string, string> = {
  image: "图片", video: "视频", voice: "语音", file: "文件", emoji: "表情",
  location: "位置", quote: "引用", appmsg: "链接/富载体", contact_card: "名片",
};
function isRich(m: any) {
  return m.msg_type !== "text" && m.msg_type !== "system";
}
function iconOf(m: any) {
  return TYPE_LABEL[m.msg_type] || "附件";
}

onMounted(async () => {
  const { data } = await listSessions();
  sessions.value = data;
  try {
    customers.value = (await listCustomers()).data;
  } catch { /* ignore */ }
  if (route.query.session_id) {
    sessionId.value = Number(route.query.session_id);
    load();
  }
});

watch([sessionId, senderType], load, { deep: true });

async function load(append = false) {
  const params: Record<string, unknown> = { limit: 50 };
  if (sessionId.value) params.session_id = sessionId.value;
  if (q.value) params.q = q.value;
  if (senderType.value) params.sender_type = senderType.value;
  if (append && nextCursor.value) params.cursor = nextCursor.value;
  if (senderWxid.value) params.sender_wxid = senderWxid.value;
  if (customerId.value) params.customer_id = customerId.value;
  if (dateRange.value) {
    params.from_ts = dateRange.value[0] + " 00:00:00";
    params.to_ts = dateRange.value[1] + " 23:59:59";
  }
  const { data } = await searchMessages(params);
  items.value = append ? [...items.value, ...data.items] : data.items;
  nextCursor.value = data.next_cursor;
}

async function openTagDialog(m: any) {
  tagMsg.value = m;
  tagInput.value = "";
  tagDialog.value = true;
}
async function addTag() {
  const t = tagInput.value.trim();
  if (!t || !tagMsg.value) return;
  const r = await addMessageTag(tagMsg.value.id, t);
  tagMsg.value.tags = r.data.tags;
  tagInput.value = "";
}
async function removeTag(m: any, t: string) {
  const r = await deleteMessageTag(m.id, t);
  m.tags = r.data.tags;
}

async function doExport() {
  if (!sessionId.value) return;
  const resp = await exportSessionCsv(sessionId.value);
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `session-${sessionId.value}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

async function showContext(row: any) {
  contextMsg.value = (await messageContext(row.id, 10, 10)).data;
}
</script>

<template>
  <div>
    <div class="page-head">
      <div class="page-kicker">业务 · 消息检索</div>
      <h1 class="page-title">消息检索</h1>
      <div class="page-standfirst">按客户、关键词、时间、方向，定位任何一段对话——10 万条 &lt;2s。</div>
    </div>

    <section class="section">
      <div class="section-head" style="margin-top:0">
        <span class="section-no">01</span>
        <span class="section-title">检索条件</span>
        <span class="section-note">检索与导出均记入审计</span>
      </div>
      <div class="card" style="display: flex; gap: 12px">
      <el-select v-model="customerId" placeholder="按客户" style="width: 160px" clearable
                 @change="sessionId = null; load()">
        <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
      </el-select>
      <el-select v-model="sessionId" placeholder="全部会话" style="width: 240px" filterable clearable>
        <el-option v-for="s in sessions" :key="s.id" :label="s.name || s.wx_id" :value="s.id" />
      </el-select>
      <el-input v-model="q" placeholder="关键词检索（≥3 字全文检索，2 字模糊）"
                style="flex: 1" clearable @change="load()" />
      <el-select v-model="senderType" placeholder="方向" style="width: 120px" clearable>
        <el-option v-for="(label, key) in SENDER_LABEL" :key="key" :label="label" :value="key" />
      </el-select>
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
                      start-placeholder="开始日期" end-placeholder="结束日期" style="width: 240px" />
      <el-input v-model="senderWxid" placeholder="发送者 wxid（精确）" style="width: 170px"
                clearable @change="load()" />
      <el-button type="primary" @click="load()">检索</el-button>
      <el-button :disabled="!sessionId" @click="doExport">导出本会话 CSV</el-button>
    </div>
    <div class="card" style="padding: 8px 12px; margin-top: 12px">
      <span style="color: var(--ink-3, #6e675c); font-size:12px">
        提示：点击消息下方的「标注」可给关键消息打标签（如「报价」「承诺」），客户详情页会按标签汇总。
      </span>
    </div>
    </section>

    <section class="section">
      <div class="section-head" style="margin-top:0">
        <span class="section-no">02</span>
        <span class="section-title">会话流</span>
        <span class="section-note">按时间正序 · 点击消息查看上下文</span>
      </div>
      <div class="card flow">
      <div v-for="m in items" :key="m.id" class="msg" :class="m.sender_type" @click="showContext(m)">
        <div class="meta">
          {{ new Date(m.ts).toLocaleString() }} · {{ SENDER_LABEL[m.sender_type] || m.sender_type }}
          <el-tag v-if="m.recalled" size="small" type="info">已撤回</el-tag>
        </div>
        <div v-if="m.tags?.length" class="tags">
          <el-tag v-for="t in m.tags" :key="t" size="small" type="warning" closable
                  @close="removeTag(m, t)">#{{ t }}</el-tag>
        </div>
        <div v-if="m.msg_type === 'text'" class="content">{{ m.content }}</div>
        <div v-else-if="m.msg_type !== 'system'" class="content rich">
          <span class="chip">{{ iconOf(m) }} {{ m.content }}</span>
          <a v-if="m.media_meta?.url" :href="m.media_meta.url" target="_blank"
             rel="noopener" class="link">查看链接 ↗</a>
        </div>
        <el-button class="tagbtn" link size="small" @click="openTagDialog(m)">标注</el-button>
      </div>
      <el-dialog v-model="tagDialog" title="消息标注" width="360">
        <div v-if="tagMsg" style="margin-bottom: 10px; color: #475569; font-size: 13px">
          {{ (tagMsg.content || "").slice(0, 60) }}
        </div>
        <div style="margin-bottom: 10px">
          <el-tag v-for="t in tagMsg?.tags || []" :key="t" closable style="margin-right: 6px"
                  @close="tagMsg && removeTag(tagMsg, t)">#{{ t }}</el-tag>
          <span v-if="!tagMsg?.tags?.length" style="color:#94a3b8; font-size:13px">暂无标签</span>
        </div>
        <el-input v-model="tagInput" placeholder="输入标签，如：报价 / 承诺 / 风险" @keyup.enter="addTag" />
        <template #footer>
          <el-button @click="tagDialog = false">关闭</el-button>
          <el-button type="primary" @click="addTag">添加标签</el-button>
        </template>
      </el-dialog>
      <el-empty v-if="!items.length" description="无消息（调整会话/关键词）" />
      <div style="text-align: center; margin-top: 8px" v-if="nextCursor">
        <el-button @click="load(true)">加载更多</el-button>
      </div>
      </div>
    </section>

    <el-drawer v-model="contextMsg" title="消息上下文" size="45%">
      <div v-for="m in contextMsg || []" :key="m.id" class="msg" :class="m.sender_type">
        <div class="meta">{{ new Date(m.ts).toLocaleString() }} ·
          {{ SENDER_LABEL[m.sender_type] || m.sender_type }}</div>
        <div v-if="m.tags?.length" class="tags">
          <el-tag v-for="t in m.tags" :key="t" size="small" type="warning" closable
                  @close="removeTag(m, t)">#{{ t }}</el-tag>
        </div>
        <div v-if="m.msg_type === 'text'" class="content">{{ m.content }}</div>
        <div v-else-if="m.msg_type !== 'system'" class="content rich">
          <span class="chip">{{ iconOf(m) }} {{ m.content }}</span>
          <a v-if="m.media_meta?.url" :href="m.media_meta.url" target="_blank"
             rel="noopener" class="link">查看链接 ↗</a>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.flow { max-height: calc(100vh - 220px); overflow: auto; }
.rich { display: flex; flex-direction: column; gap: 4px; align-items: flex-start; }
.chip { display: inline-block; background: #f1f5f9; border: 1px dashed #cbd5e1;
        border-radius: 8px; padding: 4px 10px; color: #475569; font-size: 13px; }
.link { font-size: 12px; color: #2563eb; text-decoration: none; }
.tags { display: flex; gap: 4px; margin-top: 2px; }
.tagbtn { opacity: 0.35; }
.msg:hover .tagbtn { opacity: 1; }
.msg { padding: 8px 12px; border-radius: 10px; margin: 6px 0; cursor: pointer; }
.msg.external { background: #fff; border: 1px solid #e2e8f0; }
.msg.internal, .msg.me { background: #e0f2fe; margin-left: 15%; }
.msg.system { background: transparent; color: #94a3b8; font-size: 12px; text-align: center; }
.msg:hover { box-shadow: 0 1px 6px rgba(0,0,0,.1); }
.meta { font-size: 11px; color: #94a3b8; }
.content { margin-top: 2px; white-space: pre-wrap; }
</style>
