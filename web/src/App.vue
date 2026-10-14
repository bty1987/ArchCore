<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuth } from "./stores/auth";
import { notifications, markNotificationsRead, dashboard } from "./api/client";
import { ElMessage } from "element-plus";

const auth = useAuth();
const route = useRoute();
const router = useRouter();
const unread = ref(0);

const navGroups = [
  { title: "业务", items: [
    { path: "/dashboard", label: "工作台" },
    { path: "/customers", label: "客户中心" },
    { path: "/sessions", label: "消息检索" },
    { path: "/alerts", label: "预警中心" },
    { path: "/insights", label: "洞察分析" },
  ]},
  { title: "系统", items: [
    { path: "/collector", label: "采集与通道" },
    { path: "/settings", label: "系统设置" },
  ]},
];
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
  <div v-if="auth.isLogged && route.path !== '/login'" class="shell">
    <header class="topbar">
      <div class="topbar-in">
        <router-link to="/dashboard" class="brand">
          <span class="brand-mark serif">ArchCore</span>
          <span class="brand-sub">客户智能经营平台</span>
        </router-link>

        <nav class="nav">
          <template v-for="(g, gi) in navGroups" :key="g.title">
            <span v-if="gi > 0" class="nav-sep" />
            <span class="nav-label">{{ g.title }}</span>
            <router-link
              v-for="m in g.items"
              :key="m.path"
              :to="m.path"
              class="nav-item"
              :class="{ active: route.path === m.path }"
            >{{ m.label }}</router-link>
          </template>
        </nav>

        <div class="top-right">
          <span class="sys" :class="sysOk ? 'ok' : 'bad'">
            <i />{{ sysOk ? "系统正常" : "检查中" }}
          </span>
          <button class="ghost" @click="openNotifications">
            通知<span v-if="unread > 0" class="dot">{{ unread }}</span>
          </button>
          <span class="user">{{ auth.username }}<span class="role">{{ auth.role }}</span></span>
          <button class="ghost" @click="logout">退出</button>
        </div>
      </div>
    </header>
    <main class="main"><router-view /></main>
    <footer class="colophon">
      <span class="serif">ArchCore</span> · 私有化部署 · 数据 100% 自有 · 永久只收不发
    </footer>
  </div>
  <router-view v-else />
</template>

<style scoped>
.shell { min-height: 100vh; display: flex; flex-direction: column; }

.topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  background: var(--paper);
  border-bottom: 1px solid var(--rule);
}
.topbar-in {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 32px;
  height: 58px;
  display: flex;
  align-items: center;
  gap: 22px;
}
.brand { display: flex; align-items: baseline; gap: 8px; text-decoration: none; }
.brand-mark { font-size: 21px; font-weight: 600; color: var(--ink); }
.brand-sub { font-size: 12px; color: var(--ink-3); letter-spacing: 0.08em; }

.nav { display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; overflow-x: auto; }
.nav-sep { width: 1px; height: 20px; background: var(--rule); margin: 0 8px; flex: none; }
.nav-label { font-size: 12px; color: var(--ink-3); letter-spacing: 0.3em; flex: none; }
.nav-item {
  font-size: 14px;
  color: var(--ink-2);
  text-decoration: none;
  padding: 18px 10px 15px;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}
.nav-item:hover { color: var(--accent-ink); }
.nav-item.active {
  color: var(--ink);
  font-weight: 600;
  border-bottom-color: var(--accent);
}

.top-right { display: flex; align-items: center; gap: 14px; flex: none; }
.sys { font-size: 12px; display: inline-flex; align-items: center; gap: 5px; }
.sys i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.sys.ok { color: #3d7a44; }
.sys.ok i { background: #3d7a44; }
.sys.bad { color: #b3402a; }
.sys.bad i { background: #b3402a; }
.ghost {
  background: none;
  border: none;
  color: var(--ink-2);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 2px;
  position: relative;
  font-family: var(--sans);
}
.ghost:hover { color: var(--accent-ink); }
.dot {
  background: var(--accent);
  color: var(--paper-card);
  border-radius: 8px;
  font-size: 11px;
  padding: 0 5px;
  margin-left: 4px;
}
.user { font-size: 13px; color: var(--ink-2); }
.user .role { color: var(--ink-3); margin-left: 4px; font-size: 12px; }

.main { flex: 1; padding-bottom: 30px; }
.colophon {
  border-top: 1px solid var(--rule);
  padding: 16px 32px 22px;
  text-align: center;
  font-size: 12px;
  color: var(--ink-3);
  max-width: 1280px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
.colophon .serif { color: var(--ink-2); }
</style>
