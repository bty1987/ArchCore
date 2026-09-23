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
const menus = [
  { path: "/dashboard", label: "仪表盘", icon: "Odometer" },
  { path: "/customers", label: "客户", icon: "User" },
  { path: "/sessions", label: "会话检索", icon: "ChatDotRound" },
  { path: "/alerts", label: "预警中心", icon: "Bell" },
  { path: "/collector", label: "采集管理", icon: "Monitor" },
  { path: "/settings", label: "系统设置", icon: "Setting" },
];

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
    <el-aside width="200px" class="side">
      <div class="logo">ArchCore</div>
      <el-menu :default-active="active" router background-color="#1f2937" text-color="#cbd5e1"
               active-text-color="#60a5fa">
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          {{ m.label }}
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="head">
        <div />
        <div class="head-right">
          <el-badge :value="unread" :hidden="unread === 0" ref="bell">
            <el-button circle text @click="openNotifications">🔔</el-button>
          </el-badge>
          <span class="user">{{ auth.username }}（{{ auth.role }}）</span>
          <el-button link @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main"><router-view /></el-main>
    </el-container>
  </el-container>
  <router-view v-else />
</template>

<style>
body { margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
.side { background: #1f2937; }
.logo { color: #fff; font-size: 20px; font-weight: 700; padding: 20px 16px; }
.head { display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1px solid #e5e7eb; }
.head-right { display: flex; align-items: center; gap: 12px; }
.user { color: #475569; font-size: 14px; }
.main { background: #f1f5f9; }
.card { background: #fff; border-radius: 12px; padding: 16px; margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,.06); }
</style>
