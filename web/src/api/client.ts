import axios from "axios";

export const api = axios.create({ baseURL: "/api/v1", timeout: 30000 });

api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem("archcore_token");
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response?.status === 401 && location.hash !== "#/login") {
      localStorage.removeItem("archcore_token");
      location.hash = "#/login";
    }
    return Promise.reject(err);
  }
);

// —— 认证 ——
export const login = (username: string, password: string) =>
  api.post("/auth/login", { username, password });
export const me = () => api.get("/auth/me");

// —— 客户/会话 ——
export const listCustomers = (params?: object) => api.get("/customers", { params });
export const createCustomer = (data: object) => api.post("/customers", data);
export const updateCustomer = (id: number, data: object) => api.put(`/customers/${id}`, data);
export const deleteCustomer = (id: number) => api.delete(`/customers/${id}`);
export const claimSessions = (id: number, sessionIds: number[]) =>
  api.post(`/customers/${id}/claim`, { session_ids: sessionIds });
export const exportCustomerCsv = (id: number) =>
  api.get(`/customers/${id}/export/csv`, { responseType: "blob" });
export const listSessions = (params?: object) => api.get("/sessions", { params });
export const listUnclaimed = () => api.get("/sessions/unclaimed");
export const mapSession = (id: number, customerId: number | null) =>
  api.post(`/sessions/${id}/map`, { customer_id: customerId });

// —— 消息 ——
export const searchMessages = (params: Record<string, unknown>) =>
  api.get("/messages", { params });
export const messageContext = (id: number, before = 20, after = 20) =>
  api.get(`/messages/${id}/context`, { params: { before, after } });

// —— 分析 ——
export const dashboard = () => api.get("/dashboard");
export const trends = (params?: object) => api.get("/analytics/trends", { params });
export const customerOverview = (id: number) => api.get(`/analytics/customers/${id}/overview`);
export const keywordStats = (days = 30) =>
  api.get("/analytics/keywords/stats", { params: { days } });
export const exportSessionCsv = (id: number) =>
  api.get(`/sessions/${id}/export/csv`, { responseType: "blob" });
export const addMessageTag = (id: number, tag: string) =>
  api.post(`/messages/${id}/tags`, { tag });
export const deleteMessageTag = (id: number, tag: string) =>
  api.delete(`/messages/${id}/tags/${encodeURIComponent(tag)}`);
export const getCustomerSummary = (id: number) =>
  api.get(`/analytics/customers/${id}/summary`);
export const generateCustomerSummary = (id: number, days: number) =>
  api.post(`/analytics/customers/${id}/summary`, { days });

// —— 预警/通知 ——
export const listAlerts = (params?: object) => api.get("/alerts", { params });
export const handleAlert = (id: number, action: string, note: string) =>
  api.post(`/alerts/${id}/handle`, { action, note });
export const listAlertRules = () => api.get("/alert-rules");
export const updateAlertRule = (code: string, data: object) =>
  api.put(`/alert-rules/${code}`, data);
export const notifications = () => api.get("/notifications");
export const markNotificationsRead = () => api.post("/notifications/read");
export const listChannels = () => api.get("/notify-channels");
export const createChannel = (data: object) => api.post("/notify-channels", data);
export const testChannel = (id: number) => api.post(`/notify-channels/${id}/test`);

// —— 采集/管理 ——
export const ingestHealth = () => api.get("/ingest/health");
export const getWhitelist = () => api.get("/whitelist");
export const setAllowAll = (enabled: boolean) =>
  api.put("/whitelist/allow-all", { enabled });
export const addWhitelistRule = (data: object) => api.post("/whitelist", data);
export const deleteWhitelistRule = (id: number) => api.delete(`/whitelist/${id}`);
export const reportInventory = (sessions: object[]) =>
  api.post("/ingest/sessions", { sessions });
export const listSyncTasks = () => api.get("/audit-logs"); // 采集任务历史复用审计视图入口
export const listUsers = () => api.get("/users");
export const createUser = (data: object) => api.post("/users", data);
export const updateUser = (id: number, data: object) => api.put(`/users/${id}`, data);
export const listMembers = () => api.get("/members");
export const createMember = (data: object) => api.post("/members", data);
export const deleteMember = (id: number) => api.delete(`/members/${id}`);
export const listKeywords = (params?: object) => api.get("/keywords", { params });
export const createKeyword = (data: object) => api.post("/keywords", data);
export const deleteKeyword = (id: number) => api.delete(`/keywords/${id}`);
export const listAuditLogs = (params?: object) => api.get("/audit-logs", { params });
