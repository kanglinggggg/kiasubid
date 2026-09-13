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
  ProposalAnswerReviewResponse,
  ProposalDraftResponse,
  ProposalPlanResponse,
  TenderLabMode,
  TenderLabRequest,
  TenderLabResponse,
  TenderChangeSimulation,
} from "../types/tenderLab";

const DEMO_BID_ID = "BID-DEMO-001";
const STATIC_PREVIEW = import.meta.env.MODE === "pages";
let staticBidState: BidState | null = null;

async function staticJson<T>(name: string): Promise<T> {
  const response = await fetch(`${import.meta.env.BASE_URL}static-demo/${name}`);
  if (!response.ok) throw new Error("The shared visual preview could not load its demo data.");
  return response.json() as Promise<T>;
}

async function staticBid(name: string): Promise<BidState> {
  staticBidState = await staticJson<BidState>(name);
  return structuredClone(staticBidState);
}

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
  get: () => STATIC_PREVIEW ? staticBid("bid-main.json") : request<BidState>(`/api/bids/${DEMO_BID_ID}`),
  reset: () => STATIC_PREVIEW ? staticBid("bid-main.json") : request<BidState>("/api/demo/reset", { method: "POST" }),
  listFixtures: () => STATIC_PREVIEW ? staticJson<DemoFixture[]>("fixtures.json") : request<DemoFixture[]>("/api/demo/fixtures"),
  loadFixture: (fixtureId: string) =>
    STATIC_PREVIEW
      ? staticBid(`fixture-${fixtureId}.json`)
      : request<BidState>(`/api/demo/fixtures/${fixtureId}`, { method: "POST" }),
  applyCorrigendum: () =>
    STATIC_PREVIEW
      ? staticBid("amendment-applied.json")
      : request<BidState>(`/api/demo/bids/${DEMO_BID_ID}/apply-corrigendum`, {
          method: "POST",
        }),
  completeTask: (taskId: string) =>
    STATIC_PREVIEW
      ? Promise.resolve(structuredClone(staticBidState as BidState))
      : request<BidState>(`/api/tasks/${taskId}/complete`, { method: "POST" }),
};

export const tenderLabApi = {
  sample: (mode: TenderLabMode) =>
    STATIC_PREVIEW
      ? staticJson<TenderLabRequest>(`tender-${mode.toLowerCase()}.json`)
      : request<TenderLabRequest>(`/api/tender-lab/sample/${mode.toLowerCase()}`),
  analyze: (payload: TenderLabRequest) =>
    STATIC_PREVIEW
      ? staticJson<TenderLabResponse>(`analysis-${payload.mode.toLowerCase()}.json`)
      : request<TenderLabResponse>("/api/tender-lab/analyze", {
          method: "POST",
          body: JSON.stringify(payload),
        }),
  extract: (file: File) => {
    if (STATIC_PREVIEW) {
      return Promise.reject(new Error("Document upload is available in the local full-stack demo."));
    }
    const form = new FormData();
    form.append("file", file);
    return request<DocumentExtractionResponse>("/api/tender-lab/extract", {
      method: "POST",
      body: form,
    });
  },
  companyProfile: (file: File) => {
    if (STATIC_PREVIEW) {
      return Promise.reject(new Error("ACRA upload is available in the local full-stack demo."));
    }
    const form = new FormData();
    form.append("file", file);
    return request<BusinessProfileIngestionResult>(
      "/api/tender-lab/company-profile/extract",
      { method: "POST", body: form },
    );
  },
  awardContext: (query: string, agency?: string) => {
    if (STATIC_PREVIEW) return staticJson<AwardContextResponse>("award-context.json");
    const params = new URLSearchParams({ query });
    if (agency?.trim()) params.set("agency", agency.trim());
    return request<AwardContextResponse>(`/api/public-data/gebiz/awards?${params.toString()}`);
  },
  partnerRoute: (tender: TenderLabRequest, awardContext: AwardContextResponse) =>
    STATIC_PREVIEW
      ? staticJson<PartnerRoutePackage>("partner-route.json")
      : request<PartnerRoutePackage>("/api/tender-lab/partner-route", {
          method: "POST",
          body: JSON.stringify({ tender, award_context: awardContext }),
        }),
  simulateChange: (tender: TenderLabRequest, sourceLabel: string, amendmentText: string) =>
    STATIC_PREVIEW
      ? staticJson<TenderChangeSimulation>("change-simulation.json")
      : request<TenderChangeSimulation>("/api/tender-lab/simulate-change", {
          method: "POST",
          body: JSON.stringify({
            tender,
            source_label: sourceLabel,
            amendment_text: amendmentText,
          }),
        }),
  agentLoop: (tender: TenderLabRequest, maxRevisionRounds = 1) =>
    STATIC_PREVIEW
      ? staticJson<AgentLoopResponse>("agent-loop.json")
      : request<AgentLoopResponse>("/api/tender-lab/agent-loop", {
          method: "POST",
          body: JSON.stringify({ tender, max_revision_rounds: maxRevisionRounds }),
        }),
  proposalPlan: (tender: TenderLabRequest) =>
    STATIC_PREVIEW
      ? staticJson<ProposalPlanResponse>("proposal-plan.json")
      : request<ProposalPlanResponse>("/api/tender-lab/proposal/plan", {
          method: "POST",
          body: JSON.stringify({ tender }),
        }),
  reviewProposalAnswer: (tender: TenderLabRequest, questionId: string, answer: string) =>
    STATIC_PREVIEW
      ? staticJson<ProposalAnswerReviewResponse>("proposal-review.json")
      : request<ProposalAnswerReviewResponse>("/api/tender-lab/proposal/review-answer", {
          method: "POST",
          body: JSON.stringify({ tender, question_id: questionId, answer }),
        }),
  generateProposalDraft: (tender: TenderLabRequest) =>
    STATIC_PREVIEW
      ? staticJson<ProposalDraftResponse>("proposal-draft.json")
      : request<ProposalDraftResponse>("/api/tender-lab/proposal/draft", {
          method: "POST",
          body: JSON.stringify({ tender }),
        }),
};

export const amendmentApi = {
  preview: (bidId: string, payload: AmendmentPreviewRequest) =>
    STATIC_PREVIEW
      ? staticJson<AmendmentPreviewResponse>("amendment-preview.json")
      : request<AmendmentPreviewResponse>(`/api/bids/${bidId}/amendments/preview`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
  apply: (bidId: string, payload: AmendmentApplyRequest) =>
    STATIC_PREVIEW
      ? staticBid("amendment-applied.json")
      : request<AmendmentApplyResponse>(`/api/bids/${bidId}/amendments/apply`, {
          method: "POST",
          body: JSON.stringify(payload),
        }),
};
