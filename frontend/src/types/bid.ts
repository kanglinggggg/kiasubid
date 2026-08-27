export type OperationalStatus = "FEASIBLE" | "RECOVERABLE" | "BLOCKED" | "UNCERTAIN";
export type AssessmentStatus = "SATISFIED" | "PARTIAL" | "UNMET" | "UNCERTAIN" | "SUPERSEDED";
export type GateType = "MANDATORY" | "SCORED" | "INFORMATIONAL";
export type VerificationStatus = "VERIFIED" | "STALE" | "MISSING" | "UNVERIFIED";
export type AvailabilityStatus = "AVAILABLE" | "UNAVAILABLE" | "UNKNOWN";

export interface DemoFixture {
  id: string;
  label: string;
  description: string;
  expected_status: OperationalStatus;
}

export interface Evidence {
  id: string;
  title: string;
  type: string;
  status: VerificationStatus;
  subject_name: string | null;
  valid_until: string | null;
}

export interface RequirementHistory {
  id: string;
  version: number;
  text: string;
  assessment: AssessmentStatus;
  reason: string;
  assessed_at: string | null;
}

export interface Requirement {
  id: string;
  stable_key: string;
  version: number;
  text: string;
  requirement_type: string;
  gate_type: GateType;
  assessment: AssessmentStatus;
  assessment_reason: string;
  assessment_method: string | null;
  assessed_at: string | null;
  evidence_count: number;
  evidence: Evidence[];
  source: {
    document: string;
    page: number;
    section: string;
    snippet: string;
  };
  history: RequirementHistory[];
}

export interface BidTask {
  id: string;
  requirement_id: string | null;
  title: string;
  description: string;
  owner: string;
  status: "OPEN" | "IN_PROGRESS" | "WAITING" | "DONE" | "BLOCKED";
  priority: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  due_at: string;
  latest_safe_at: string | null;
  estimated_duration_hours: number;
  recovery_path: boolean;
  depends_on: string[];
}

export interface ActivityEvent {
  id: string;
  event_type: string;
  actor: string;
  entity_id: string | null;
  summary: string;
  timestamp: string;
}

export interface BidState {
  bid: {
    id: string;
    title: string;
    agency: string;
    reference_number: string;
    closing_at: string;
    source_type: string;
    synthetic: boolean;
    fixture_id: string;
  };
  company: {
    id: string;
    name: string;
    uen: string;
    industry: string;
    employee_count: number;
    annual_revenue: string;
  };
  interpretation: {
    mode: "BEDROCK" | "GROQ" | "DEMO_FALLBACK";
    label: "Bedrock" | "Groq" | "Demo fallback";
    model_id: string | null;
    source: "persisted_activity" | "no_persisted_interpretation";
    event_id: string | null;
  };
  metrics: {
    operational_status: OperationalStatus;
    previous_operational_status: OperationalStatus | null;
    critical_gates_verified: number;
    critical_gates_total: number;
    submission_coverage: number;
    deadline_risk: "LOW" | "MEDIUM" | "HIGH" | "MISSED";
  };
  calculations: {
    operational_feasibility: {
      status: OperationalStatus;
      reason: string;
      precedence: OperationalStatus[];
      mandatory_total: number;
      unresolved: Array<{
        requirement_id: string;
        stable_key: string;
        assessment_status: AssessmentStatus;
        recovery_task_ids: string[];
        recovery_viable: boolean;
      }>;
      persisted_value: OperationalStatus;
      matches_persisted_value: boolean;
    };
    critical_gates: {
      verified: number;
      total: number;
      rule: string;
      gates: Array<{
        requirement_id: string;
        stable_key: string;
        requirement_version: number;
        assessment_id: string | null;
        assessment_status: AssessmentStatus;
        verified: boolean;
      }>;
    };
    submission_coverage: {
      display_percent: number;
      raw_percent: number;
      formula: string;
      rounding: string;
      warning: string;
      persisted_value: number;
      matches_persisted_value: boolean;
      components: Record<
        "requirements" | "evidence" | "tasks",
        {
          label: string;
          weight: number;
          percent: number;
          weighted_points: number;
          completed_units: number;
          total_units: number;
          unit_label: string;
          rule: string;
        }
      >;
    };
    deadline_risk: {
      risk: "LOW" | "MEDIUM" | "HIGH" | "MISSED";
      calculated_at: string;
      driver_task_id: string | null;
      driver_task_title: string | null;
      minimum_slack_hours: number | null;
      formula: string;
      thresholds: Record<string, string>;
      persisted_value: "LOW" | "MEDIUM" | "HIGH" | "MISSED";
      matches_persisted_value: boolean;
      tasks: Array<{
        task_id: string;
        title: string;
        status: string;
        latest_finish: string;
        latest_start: string;
        duration_hours: number;
        slack_hours: number;
      }>;
    };
  };
  requirements: Requirement[];
  tasks: BidTask[];
  critical_actions: BidTask[];
  latest_change: null | {
    id: string;
    title: string;
    summary: string;
    stable_key: string;
    old: string;
    new: string;
    old_count: number;
    new_count: number;
    old_requirement_id: string;
    new_requirement_id: string;
    old_assessment: AssessmentStatus;
    new_assessment: AssessmentStatus;
    impact: {
      critical_gates_broken: number;
      assessments_superseded: number;
      recovery_paths_found: number;
    };
    detected_at: string;
  };
  impact_chain: Array<{ label: string; detail: string }>;
  recovery_candidate: null | {
    id: string;
    name: string;
    role: string;
    certification: VerificationStatus;
    certification_valid_until: string | null;
    cv: VerificationStatus;
    availability: AvailabilityStatus;
    can_satisfy_now: boolean;
  };
  activity_events: ActivityEvent[];
  human_review: {
    required: boolean;
    approved: boolean;
    approved_by: string | null;
    approved_at: string | null;
  };
  disclaimer: string;
}
