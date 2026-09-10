import type { BidState } from "./bid";

export interface AmendmentSourceInput {
  document_name: string;
  document_version: number;
  page: number;
  section: string;
  text: string;
}

export interface AmendmentPreviewRequest {
  requirement_id: string;
  source: AmendmentSourceInput;
}

export type AmendmentPreviewState =
  | "PREVIEW_READY"
  | "REVIEW_REQUIRED"
  | "NO_TRACKED_CHANGE";

export interface AmendmentRequirementSnapshot {
  id: string;
  stable_key: string;
  version: number;
  text: string;
  requirement_type: string;
  gate_type: string;
  minimum_count: number | null;
  certification: string | null;
  assessment: string;
}

export interface AmendmentPlannedTask {
  key: string;
  title: string;
  description: string;
  owner: string;
  status: "OPEN" | "WAITING";
  priority: "CRITICAL" | "HIGH";
  due_at: string;
  latest_safe_at: string;
  estimated_duration_hours: number;
  depends_on: string[];
}

export interface AmendmentPreviewResponse {
  preview_id: string;
  state: AmendmentPreviewState;
  apply_allowed: boolean;
  block_reason: string | null;
  source: {
    document_name: string;
    document_version: number;
    page: number;
    section: string;
    exact_excerpt: string;
    sha256: string;
    provenance: "USER_SUPPLIED_EXACT_TEXT";
  };
  target: AmendmentRequirementSnapshot;
  proposed: AmendmentRequirementSnapshot | null;
  change_type: "ADDED" | "MODIFIED" | "REMOVED" | "UNCHANGED";
  changed_fields: Array<{
    field: string;
    old_value: string;
    new_value: string;
  }>;
  reason_summary: string;
  interpretation_mode: "BEDROCK" | "GROQ" | "DEMO_FALLBACK";
  model_id: string | null;
  fallback_reason: string | null;
  impact: null | {
    assessment_before: string;
    assessment_after: string;
    operational_status_before: string;
    operational_status_after: string;
    critical_gates_before: string;
    critical_gates_after: string;
    submission_coverage_before: number;
    submission_coverage_after: number;
    deadline_risk_before: string;
    deadline_risk_after: string;
    calculation_note: string;
  };
  planned_tasks: AmendmentPlannedTask[];
  clarification: null | {
    reason: string;
    question: string;
    source_reference: string;
    external_action: "COPY_ONLY";
  };
  workflow_trace: Array<{
    step: number;
    node: string;
    status: "DONE" | "BLOCKED" | "SKIPPED";
    detail: string;
  }>;
  human_checkpoint: string;
  expires_in_minutes: number;
}

export interface AmendmentApplyRequest {
  preview_id: string;
  reviewed_source_and_diff: true;
  confirmed_by: string;
}

export type AmendmentApplyResponse = BidState;
