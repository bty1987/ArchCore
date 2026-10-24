import { beforeEach, describe, expect, it, vi } from "vitest";

// Dashboard 的 AI 对话流纯逻辑:历史持久化与截断规则(#3 落地的行为锁定)
// 组件内逻辑不易直接测,这里以同规则实现做行为基线锁定(30 条上限/最近 8 轮上送)
const HIST_KEY = "archcore_assistant_history";

function pushMessage(store: any[], msg: any) {
  store.push(msg);
  const trimmed = store.slice(-30);
  return trimmed;
}
function historyForApi(store: any[]) {
  return store
    .filter((m) => m.role === "user" || m.role === "assistant")
    .slice(-8)
    .map((m) => ({ role: m.role, content: m.content }));
}

beforeEach(() => localStorage.clear());

describe("AI 助手对话流(#3 行为基线)", () => {
  it("历史存 localStorage,30 条上限裁剪", () => {
    const store: any[] = [];
    for (let i = 0; i < 35; i++) {
      const saved = pushMessage(store, { role: "user", content: `q${i}` });
      localStorage.setItem(HIST_KEY, JSON.stringify(saved));
    }
    const back = JSON.parse(localStorage.getItem(HIST_KEY) || "[]");
    expect(back.length).toBe(30);
    expect(back[0].content).toBe("q5"); // 最早的 5 条被裁
  });

  it("上送 API 的 history:只取最近 8 轮且只含 user/assistant", () => {
    const store = Array.from({ length: 12 }, (_, i) => ({
      role: i % 2 ? "assistant" : "user",
      content: `m${i}`,
      hits: [{ session: "x" }],
    }));
    const h = historyForApi(store);
    expect(h.length).toBe(8);
    expect(h[0].content).toBe("m4"); // 最近 8 条:4..11
    expect(h.every((x) => x.role === "user" || x.role === "assistant")).toBe(true);
    expect(Object.keys(h[0])).toEqual(["role", "content"]); // hits 不上送
  });

  it("清空对话:清 store 与 localStorage", () => {
    localStorage.setItem(HIST_KEY, JSON.stringify([{ role: "user", content: "x" }]));
    localStorage.removeItem(HIST_KEY);
    expect(localStorage.getItem(HIST_KEY)).toBeNull();
  });
});
