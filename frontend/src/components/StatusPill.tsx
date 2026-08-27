import { AlertTriangle, Check, CircleHelp, Clock3, X } from "lucide-react";
import type {
  AssessmentStatus,
  AvailabilityStatus,
  OperationalStatus,
  VerificationStatus,
} from "../types/bid";

type Status =
  | OperationalStatus
  | AssessmentStatus
  | VerificationStatus
  | AvailabilityStatus
  | "MANDATORY"
  | "SCORED"
  | "INFORMATIONAL"
  | "LOW"
  | "MEDIUM"
  | "HIGH"
  | "MISSED";

const positive = new Set(["FEASIBLE", "SATISFIED", "VERIFIED", "AVAILABLE", "LOW"]);
const warning = new Set(["RECOVERABLE", "PARTIAL", "STALE", "MEDIUM"]);
const negative = new Set([
  "BLOCKED",
  "UNMET",
  "MISSING",
  "UNAVAILABLE",
  "HIGH",
  "MISSED",
]);

export function StatusPill({ status, compact = false }: { status: Status; compact?: boolean }) {
  const tone = positive.has(status)
    ? "positive"
    : warning.has(status)
      ? "warning"
      : negative.has(status)
        ? "negative"
        : status === "MANDATORY"
          ? "mandatory"
          : "neutral";
  const Icon = positive.has(status)
    ? Check
    : negative.has(status)
      ? X
      : warning.has(status)
        ? AlertTriangle
        : status === "UNCERTAIN" || status === "UNVERIFIED" || status === "UNKNOWN"
          ? CircleHelp
          : Clock3;

  return (
    <span className={`status-pill status-${tone} ${compact ? "status-compact" : ""}`}>
      {!compact && <Icon size={12} strokeWidth={2.6} />}
      {status.replaceAll("_", " ")}
    </span>
  );
}
