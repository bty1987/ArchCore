import { defineStore } from "pinia";
import { login as apiLogin, me } from "../api/client";

export const useAuth = defineStore("auth", {
  state: () => ({
    token: localStorage.getItem("archcore_token") || "",
    username: localStorage.getItem("archcore_username") || "",
    role: localStorage.getItem("archcore_role") || "",
  }),
  getters: {
    isLogged: (s) => !!s.token,
    isManager: (s) => s.role === "admin" || s.role === "manager",
    isAdmin: (s) => s.role === "admin",
  },
  actions: {
    async login(username: string, password: string) {
      const { data } = await apiLogin(username, password);
      this.token = data.token;
      this.role = data.role;
      // 拦截器从 localStorage 取 token，必须先落盘再发起带认证的请求（如 /auth/me）
      localStorage.setItem("archcore_token", data.token);
      localStorage.setItem("archcore_role", data.role);
      const meResp = await me();
      this.username = meResp.data.username;
      localStorage.setItem("archcore_username", this.username);
      return data; // 含 must_change_password(P0 #9)
    },
    logout() {
      this.token = "";
      this.role = "";
      this.username = "";
      localStorage.removeItem("archcore_token");
      localStorage.removeItem("archcore_role");
      localStorage.removeItem("archcore_username");
    },
  },
});
