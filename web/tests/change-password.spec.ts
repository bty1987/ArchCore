import { describe, expect, it, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";

const mockChange = vi.hoisted(() => vi.fn());
const mockRouterPush = vi.hoisted(() => vi.fn());
const mockLogout = vi.hoisted(() => vi.fn());

vi.mock("../src/api/client", () => ({ changePassword: mockChange }));
vi.mock("../src/stores/auth", () => ({ useAuth: () => ({ logout: mockLogout }) }));
vi.mock("vue-router", () => ({ useRouter: () => ({ push: mockRouterPush }) }));

import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import ChangePassword from "../src/views/ChangePassword.vue";

function mountForm() {
  return mount(ChangePassword, {
    global: { plugins: [ElementPlus] },
  });
}

function inputs(w: any) {
  return w.findAll("input");
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ChangePassword", () => {
  it("三次输入齐全且一致前按钮 disabled", async () => {
    const w = mountForm();
    const [oldI, new1, new2] = inputs(w);
    await oldI.setValue("oldpass1");
    await new1.setValue("short");
    expect((w.vm as any).pwdReady).toBe(false); // 不足 8 位
    await new1.setValue("longenough8");
    expect((w.vm as any).pwdReady).toBe(false); // 未确认
    await new2.setValue("longenough8");
    await flushPromises();
    expect((w.vm as any).pwdReady).toBe(true);
  });

  it("提交成功 → logout + 跳登录", async () => {
    mockChange.mockResolvedValue({ data: { ok: true } });
    const w = mountForm();
    const [oldI, new1, new2] = inputs(w);
    await oldI.setValue("oldpass1");
    await new1.setValue("longenough8");
    await new2.setValue("longenough8");
    await (w.vm as any).submit();
    await flushPromises();
    expect(mockChange).toHaveBeenCalledWith("oldpass1", "longenough8");
    expect(mockLogout).toHaveBeenCalled();
    expect(mockRouterPush).toHaveBeenCalledWith("/login");
  });

  it("提交失败 → 不跳转", async () => {
    mockChange.mockRejectedValue({ response: { data: { detail: "旧密码错误" } } });
    const w = mountForm();
    const [oldI, new1, new2] = inputs(w);
    await oldI.setValue("wrong");
    await new1.setValue("longenough8");
    await new2.setValue("longenough8");
    await (w.vm as any).submit();
    await flushPromises();
    expect(mockLogout).not.toHaveBeenCalled();
    expect(mockRouterPush).not.toHaveBeenCalled();
  });
});
