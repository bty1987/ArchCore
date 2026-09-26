import { createRouter, createWebHashHistory } from "vue-router";
import { useAuth } from "./stores/auth";

const routes = [
  { path: "/login", component: () => import("./views/Login.vue"), meta: { public: true } },
  { path: "/", redirect: "/dashboard" },
  { path: "/dashboard", component: () => import("./views/Dashboard.vue") },
  { path: "/customers", component: () => import("./views/CustomerList.vue") },
  { path: "/customers/:id", component: () => import("./views/CustomerDetail.vue") },
  { path: "/sessions", component: () => import("./views/SessionBrowser.vue") },
  { path: "/alerts", component: () => import("./views/AlertCenter.vue") },
  { path: "/insights", component: () => import("./views/Insights.vue") },
  { path: "/collector", component: () => import("./views/CollectorPanel.vue") },
  { path: "/settings", component: () => import("./views/Settings.vue") },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuth();
  if (!to.meta.public && !auth.isLogged) return "/login";
  return true;
});
