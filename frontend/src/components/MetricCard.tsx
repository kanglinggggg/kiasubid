import type { LucideIcon } from "lucide-react";
import { ArrowRight } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string;
  caption: string;
  icon: LucideIcon;
  tone: "green" | "amber" | "red" | "blue" | "slate";
  previous?: string | null;
  hero?: boolean;
}
export function MetricCard({
  label,
  value,
  caption,
  icon: Icon,
  tone,
  previous,
  hero = false,
}: MetricCardProps) {
  return (
    <article className={`metric-card metric-${tone} ${hero ? "metric-hero" : ""}`}>
      <div className="metric-topline">
        <span>{label}</span>
        <span className="metric-icon">
          <Icon size={18} />
        </span>
      </div>
      <div className="metric-value-row">
        {previous && previous !== value && (
          <>
            <span className="metric-previous">{previous}</span>
            <ArrowRight size={17} className="metric-arrow" />
          </>
        )}
        <strong className="metric-value">{value}</strong>
      </div>
      <p>{caption}</p>
    </article>
  );
}
