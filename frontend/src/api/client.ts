import type { BidState, DemoFixture } from "../types/bid";

const DEMO_BID_ID = "BID-DEMO-001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}.`);
  }
  return response.json() as Promise<T>;
}

export const bidApi = {
  get: () => request<BidState>(`/api/bids/${DEMO_BID_ID}`),
  reset: () => request<BidState>("/api/demo/reset", { method: "POST" }),
  listFixtures: () => request<DemoFixture[]>("/api/demo/fixtures"),
  loadFixture: (fixtureId: string) =>
    request<BidState>(`/api/demo/fixtures/${fixtureId}`, { method: "POST" }),
  applyCorrigendum: () =>
    request<BidState>(`/api/demo/bids/${DEMO_BID_ID}/apply-corrigendum`, {
      method: "POST",
    }),
  completeTask: (taskId: string) =>
    request<BidState>(`/api/tasks/${taskId}/complete`, { method: "POST" }),
  approve: () =>
    request<BidState>(`/api/bids/${DEMO_BID_ID}/human-approve`, {
      method: "POST",
      body: JSON.stringify({
        approved_by: "Demo Reviewer",
        note: "Internal package reviewed during the hackathon demonstration.",
      }),
    }),
};
