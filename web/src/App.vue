<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuth } from "./stores/auth";
import { notifications, markNotificationsRead } from "./api/client";
import { ElMessage } from "element-plus";

const auth = useAuth();
const route = useRoute();
const router = useRouter();
const unread = ref(0);
const bell = ref();

const active = computed(() => route.path);
const menuGroups = [
  { title: "业务", items: [
    { path: "/dashboard", label: "工作台", icon: "🏠" },
    { path: "/customers", label: "客户中心", icon: "👤" },
    { path: "/sessions", label: "消息检索", icon: "💬" },
    { path: "/alerts", label: "预警中心", icon: "🔔" },
    { path: "/insights", label: "洞察分析", icon: "📈" },
  ]},
  { title: "系统", items: [
    { path: "/collector", label: "采集与通道", icon: "📡" },
    { path: "/settings", label: "系统设置", icon: "⚙️" },
  ]},
];
const currentTitle = computed(() => {
  for (const g of menuGroups) {
    const m = g.items.find((i) => i.path === route.path);
    if (m) return m.label;
  }
  return "ArchCore";
});
const sysOk = ref(true);
async function checkSys() {
  try {
    await dashboard();
    sysOk.value = true;
  } catch {
    sysOk.value = false;
  }
}

async function refreshUnread() {
  try {
    const { data } = await notifications();
    unread.value = data.unread;
  } catch {
    /* 未登录时静默 */
  }
}
refreshUnread();
setInterval(refreshUnread, 30000);
checkSys();
setInterval(checkSys, 60000);

async function openNotifications() {
  const { data } = await notifications();
  const html = data.items
    .slice(0, 10)
    .map((n) => `<div style="margin:6px 0"><b>${n.title}</b><br/>${n.body}</div>`)
    .join("");
  ElMessage({
    message: html || "暂无通知",
    type: "info",
    duration: 8000,
    showClose: true,
    dangerouslyUseHTMLString: true,
  });
  if (data.unread > 0) {
    await markNotificationsRead();
    unread.value = 0;
  }
}

function logout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <el-container v-if="auth.isLogged && route.path !== '/login'" style="height: 100vh">
    <el-aside width="210px" class="side">
      <div class="logo">ArchCore<span class="logo-sub">客户会话管理台</span></div>
      <el-scrollbar>
        <div v-for="g in menuGroups" :key="g.title" class="menu-group">
          <div class="group-title">{{ g.title }}</div>
          <el-menu :default-active="active" router background-color="transparent" text-color="#cbd5e1"
                   active-text-color="#60a5fa">
            <el-menu-item v-for="m in g.items" :key="m.path" :index="m.path">
              <span>{{ m.icon }} {{ m.label }}</span>
            </el-menu-item>
          </el-menu>
        </div>
      </el-scrollbar>
      <div class="side-foot">
        <el-badge :value="unread" :hidden="unread === 0">
          <el-button size="small" text style="color:#cbd5e1" @click="openNotifications">🔔 通知</el-button>
        </el-badge>
        <el-button size="small" text style="color:#cbd5e1" @click="logout">退出</el-button>
      </div>
    </el-aside>
    <el-container>
      <el-header class="head">
        <div class="head-title">{{ currentTitle }}</div>
        <div class="head-right">
          <el-tag v-if="sysOk" type="success" effect="dark" size="small" style="border:none">● 系统正常</el-tag>
          <el-tag v-else type="danger" effect="dark" size="small" style="border:none">● 检查中</el-tag>
          <span class="user">{{ auth.username }}（{{ auth.role }}）</span>
        </div>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
  <router-view v-else />
</template>

<style>
body { margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
.side { background: #111827; display: flex; flex-direction: column; }
.logo { color: #fff; font-size: 19px; font-weight: 700; padding: 18px 16px 6px; }
.logo-sub { display: block; font-size: 11px; color: #6b7280; font-weight: 400; margin-top: 2px; }
.menu-group { margin-top: 6px; }
.group-title { color: #6b7280; font-size: 11px; padding: 10px 18px 4px; letter-spacing: 2px; }
.side .el-menu { border-right: none; }
.side .el-menu-item { height: 42px; line-height: 42px; }
.side-foot { margin-top: auto; padding: 12px 16px; border-top: 1px solid #1f2937;
             display: flex; gap: 8px; align-items: center; }
.head { display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1px solid #e5e7eb; background: #fff; }
.head-title { font-size: 15px; font-weight: 600; color: #1e293b; }
.head-right { display: flex; align-items: center; gap: 12px; }
.user { color: #475569; font-size: 14px; }
.main { background: #f1f5f9; }
.card { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,.06); }
</style>
