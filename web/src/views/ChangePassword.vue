<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { changePassword } from "../api/client";
import { useAuth } from "../stores/auth";
import { ElMessage } from "element-plus";

const auth = useAuth();
const router = useRouter();
const oldPassword = ref("");
const newPassword = ref("");
const confirm = ref("");
const loading = ref(false);

const strengthOk = computed(() => newPassword.value.length >= 8);
const matchOk = computed(() => newPassword.value === confirm.value);

async function submit() {
  if (!strengthOk.value) {
    ElMessage.warning("新密码至少 8 位");
    return;
  }
  if (!matchOk.value) {
    ElMessage.warning("两次输入的新密码不一致");
    return;
  }
  loading.value = true;
  try {
    await changePassword(oldPassword.value, newPassword.value);
    ElMessage.success("密码已更新，请用新密码重新登录");
    auth.logout();
    router.push("/login");
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || "修改失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="wrap">
    <el-card class="box">
      <h2 class="serif">设置新密码</h2>
      <p class="tip">
        当前使用的是初始默认密码。为保障客户数据安全，请先设置新密码再进入系统。
      </p>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="oldPassword" type="password" placeholder="当前密码" show-password />
        </el-form-item>
        <el-form-item>
          <el-input v-model="newPassword" type="password" placeholder="新密码（至少 8 位）" show-password />
        </el-form-item>
        <el-form-item>
          <el-input v-model="confirm" type="password" placeholder="确认新密码" show-password />
        </el-form-item>
        <el-button
          type="primary"
          style="width: 100%"
          :loading="loading"
          :disabled="!strengthOk || !matchOk"
          native-type="submit"
        >
          更新密码并重新登录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--paper);
}
.box { width: 400px; border-radius: 4px; border: 1px solid var(--rule); }
.box h2 { margin: 0 0 6px; color: var(--ink); }
.tip { color: var(--ink-3); font-size: 13px; margin-bottom: 16px; }
</style>
