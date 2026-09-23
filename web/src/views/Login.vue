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
    await auth.login(username.value, password.value);
    router.push("/dashboard");
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
        background: linear-gradient(135deg, #1e3a8a33, #60a5fa33); }
.box { width: 360px; border-radius: 16px; }
.tip { color: #94a3b8; font-size: 13px; }
</style>
