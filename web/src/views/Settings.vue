<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  listUsers, createUser, updateUser, listMembers, createMember, deleteMember,
  listKeywords, createKeyword, deleteKeyword, listChannels, createChannel, testChannel,
  keywordStats,
} from "../api/client";
import { ElMessage } from "element-plus";

const tab = ref("users");
const users = ref<any[]>([]);
const members = ref<any[]>([]);
const keywords = ref<any[]>([]);
const keywordHits = ref<Record<string, number>>({});
const channels = ref<any[]>([]);

const newUser = ref({ username: "", password: "", display_name: "", role: "sales" });
const newMember = ref({ match_type: "wxid", match_value: "", display_name: "" });
const newKeyword = ref({ category: "risk", word: "" });
const newChannel = ref({ type: "wecom", name: "", webhook_url: "", min_level: "orange" });

async function load() {
  users.value = (await listUsers()).data;
  members.value = (await listMembers()).data;
  keywords.value = (await listKeywords()).data;
  try {
    const hits = (await keywordStats(30)).data as any[];
    keywordHits.value = Object.fromEntries(hits.map((h) => [h.word, h.count]));
  } catch {
    keywordHits.value = {};
  }
  try { channels.value = (await listChannels()).data; } catch { /* sales 无权限 */ }
}
onMounted(load);

async function addUser() {
  await createUser(newUser.value);
  ElMessage.success("用户已创建");
  newUser.value = { username: "", password: "", display_name: "", role: "sales" };
  load();
}
async function toggleUser(u: any) {
  await updateUser(u.id, { ...u, password: null });
  load();
}
async function addMember() {
  await createMember(newMember.value);
  newMember.value = { match_type: "wxid", match_value: "", display_name: "" };
  load();
}
async function addKeyword() {
  await createKeyword(newKeyword.value);
  newKeyword.value = { category: "risk", word: "" };
  load();
}
async function addChannel() {
  await createChannel({
    type: newChannel.value.type, name: newChannel.value.name,
    min_level: newChannel.value.min_level,
    config: { webhook_url: newChannel.value.webhook_url },
  });
  load();
}
async function test(id: number) {
  const { data } = await testChannel(id);
  ElMessage(data.status === "sent" ? "测试消息已发送" : `结果：${data.status} ${data.error || ""}`);
}
</script>

<template>
  <div class="card">
    <el-tabs v-model="tab">
      <el-tab-pane label="账号" name="users">
        <el-table :data="users" size="small">
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="display_name" label="姓名" />
          <el-table-column prop="role" label="角色" width="100" />
          <el-table-column label="启用">
            <template #default="{ row }">
              <el-switch v-model="row.enabled" @change="toggleUser(row)" />
            </template>
          </el-table-column>
        </el-table>
        <el-form inline style="margin-top: 12px">
          <el-form-item><el-input v-model="newUser.username" placeholder="用户名" /></el-form-item>
          <el-form-item><el-input v-model="newUser.password" placeholder="密码" type="password" /></el-form-item>
          <el-form-item><el-input v-model="newUser.display_name" placeholder="姓名" /></el-form-item>
          <el-form-item>
            <el-select v-model="newUser.role" style="width: 110px">
              <el-option label="销售" value="sales" /><el-option label="主管" value="manager" />
              <el-option label="管理员" value="admin" />
            </el-select>
          </el-form-item>
          <el-form-item><el-button type="primary" @click="addUser">创建</el-button></el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="内部成员名单" name="members">
        <el-table :data="members" size="small">
          <el-table-column prop="match_type" label="匹配类型" width="110" />
          <el-table-column prop="match_value" label="匹配值" />
          <el-table-column prop="display_name" label="姓名" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" @click="deleteMember(row.id); load()">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-form inline style="margin-top: 12px">
          <el-form-item>
            <el-select v-model="newMember.match_type" style="width: 110px">
              <el-option label="wxid" value="wxid" /><el-option label="昵称" value="nickname" />
              <el-option label="备注" value="remark" />
            </el-select>
          </el-form-item>
          <el-form-item><el-input v-model="newMember.match_value" placeholder="匹配值" /></el-form-item>
          <el-form-item><el-input v-model="newMember.display_name" placeholder="姓名" /></el-form-item>
          <el-form-item><el-button type="primary" @click="addMember">添加</el-button></el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="词库" name="keywords">
        <el-table :data="keywords" size="small">
          <el-table-column prop="category" label="类别" width="90" />
          <el-table-column prop="word" label="词条" />
          <el-table-column label="命中（30 天）" width="120">
            <template #default="{ row }">{{ keywordHits[row.word] ?? 0 }}</template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="danger" @click="deleteKeyword(row.id); load()">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-form inline style="margin-top: 12px">
          <el-form-item>
            <el-select v-model="newKeyword.category" style="width: 110px">
              <el-option label="风险词" value="risk" /><el-option label="关注词" value="focus" />
            </el-select>
          </el-form-item>
          <el-form-item><el-input v-model="newKeyword.word" placeholder="词条" /></el-form-item>
          <el-form-item><el-button type="primary" @click="addKeyword">添加</el-button></el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="通知渠道" name="channels">
        <el-table :data="channels" size="small">
          <el-table-column prop="type" label="类型" width="100" />
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="min_level" label="最低级别" width="100" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button link type="primary" @click="test(row.id)">测试</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-form inline style="margin-top: 12px">
          <el-form-item>
            <el-select v-model="newChannel.type" style="width: 120px">
              <el-option label="企微机器人" value="wecom" /><el-option label="邮件" value="email" />
            </el-select>
          </el-form-item>
          <el-form-item><el-input v-model="newChannel.name" placeholder="名称" /></el-form-item>
          <el-form-item>
            <el-input v-model="newChannel.webhook_url" placeholder="webhook 地址" style="width: 280px" />
          </el-form-item>
          <el-form-item><el-button type="primary" @click="addChannel">添加</el-button></el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>
