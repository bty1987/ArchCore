import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const mockApi = vi.hoisted(() => ({
  login: vi.fn(),
  me: vi.fn(),
}));
vi.mock("../src/api/client", () => ({ login: mockApi.login, me: mockApi.me, api: {} }));

import { useAuth } from "../src/stores/auth";

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  vi.clearAllMocks();
});

describe("auth store", () => {
  it("login: 落盘 token/role 并回填 username,透传 must_change_password", async () => {
    mockApi.login.mockResolvedValue({
      data: { token: "t1", role: "admin", display_name: "管理员", must_change_password: true },
    });
    mockApi.me.mockResolvedValue({ data: { username: "bty1987" } });

    const auth = useAuth();
    const data = await auth.login("admin", "pw");

    expect(data.must_change_password).toBe(true);
    expect(auth.token).toBe("t1");
    expect(auth.role).toBe("admin");
    expect(auth.username).toBe("bty1987");
    // 拦截器从 localStorage 取 token,必须先落盘再调 /auth/me
    expect(localStorage.getItem("archcore_token")).toBe("t1");
  });

  it("logout: 清空 state 与 localStorage", async () => {
    localStorage.setItem("archcore_token", "old");
    const auth = useAuth();
    auth.$patch({ token: "old", role: "admin", username: "u" });

    auth.logout();

    expect(auth.isLogged).toBe(false);
    expect(localStorage.getItem("archcore_token")).toBeNull();
    expect(localStorage.getItem("archcore_role")).toBeNull();
    expect(localStorage.getItem("archcore_username")).toBeNull();
  });

  it("getters: 角色判定", () => {
    const auth = useAuth();
    auth.$patch({ token: "t", role: "sales" });
    expect(auth.isLogged).toBe(true);
    expect(auth.isManager).toBe(false);
    expect(auth.isAdmin).toBe(false);
    auth.$patch({ role: "manager" });
    expect(auth.isManager).toBe(true);
    auth.$patch({ role: "admin" });
    expect(auth.isAdmin).toBe(true);
  });
});
