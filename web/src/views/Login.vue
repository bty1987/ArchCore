<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuth } from "../stores/auth";
import { ElMessage } from "element-plus";

const auth = useAuth();
const router = useRouter();
const username = ref("admin");
const password = ref("");
const loading = ref(false);

async function submit() {
  loading.value = true;
  try {
    const data = await auth.login(username.value, password.value);
    // 首启/默认密码 → 强制改密(改完回登录)
    router.push(data?.must_change_password ? "/change-password" : "/dashboard");
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="wrap">
    <el-card class="box">
      <h2>ArchCore 客户会话管理台</h2>
      <p class="tip">内网部署 · 数据不出客户网络</p>
      <el-form @submit.prevent="submit">
        <el-form-item><el-input v-model="username" placeholder="用户名" /></el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-button type="primary" style="width: 100%" :loading="loading" native-type="submit">
          登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.wrap { height: 100vh; display: flex; align-items: center; justify-content: center;
        background: var(--paper); }
.box { width: 380px; border-radius: 4px; border: 1px solid var(--rule); }
.tip { color: var(--ink-3); font-size: 13px; }
</style>
