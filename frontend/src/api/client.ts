import type { BidState, DemoFixture } from "../types/bid";
import type {
  AmendmentApplyRequest,
  AmendmentApplyResponse,
  AmendmentPreviewRequest,
  AmendmentPreviewResponse,
} from "../types/amendment";
import type {
  AgentLoopResponse,
  AwardContextResponse,
  BusinessProfileIngestionResult,
  DocumentExtractionResponse,
  PartnerRoutePackage,
  TenderLabMode,
  TenderLabRequest,
  TenderLabResponse,
  TenderChangeSimulation,
} from "../types/tenderLab";

const DEMO_BID_ID = "BID-DEMO-001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    headers: isFormData
      ? { ...init?.headers }
      : { "Content-Type": "application/json", ...init?.headers },
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
};

export const tenderLabApi = {
  sample: (mode: TenderLabMode) =>
    request<TenderLabRequest>(`/api/tender-lab/sample/${mode.toLowerCase()}`),
  analyze: (payload: TenderLabRequest) =>
    request<TenderLabResponse>("/api/tender-lab/analyze", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  extract: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentExtractionResponse>("/api/tender-lab/extract", {
      method: "POST",
      body: form,
    });
  },
  companyProfile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<BusinessProfileIngestionResult>(
      "/api/tender-lab/company-profile/extract",
      { method: "POST", body: form },
    );
  },
  awardContext: (query: string, agency?: string) => {
    const params = new URLSearchParams({ query });
    if (agency?.trim()) params.set("agency", agency.trim());
    return request<AwardContextResponse>(`/api/public-data/gebiz/awards?${params.toString()}`);
  },
  partnerRoute: (tender: TenderLabRequest, awardContext: AwardContextResponse) =>
    request<PartnerRoutePackage>("/api/tender-lab/partner-route", {
      method: "POST",
      body: JSON.stringify({ tender, award_context: awardContext }),
    }),
  simulateChange: (tender: TenderLabRequest, sourceLabel: string, amendmentText: string) =>
    request<TenderChangeSimulation>("/api/tender-lab/simulate-change", {
      method: "POST",
      body: JSON.stringify({
        tender,
        source_label: sourceLabel,
        amendment_text: amendmentText,
      }),
    }),
  agentLoop: (tender: TenderLabRequest, maxRevisionRounds = 1) =>
    request<AgentLoopResponse>("/api/tender-lab/agent-loop", {
      method: "POST",
      body: JSON.stringify({ tender, max_revision_rounds: maxRevisionRounds }),
    }),
};

export const amendmentApi = {
  preview: (bidId: string, payload: AmendmentPreviewRequest) =>
    request<AmendmentPreviewResponse>(`/api/bids/${bidId}/amendments/preview`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  apply: (bidId: string, payload: AmendmentApplyRequest) =>
    request<AmendmentApplyResponse>(`/api/bids/${bidId}/amendments/apply`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
