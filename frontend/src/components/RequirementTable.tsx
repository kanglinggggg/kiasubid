import { ChevronRight, Search, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import type { Requirement } from "../types/bid";
import { StatusPill } from "./StatusPill";

interface RequirementTableProps {
  requirements: Requirement[];
  selectedId: string | null;
  onSelect: (requirement: Requirement) => void;
}

type Filter = "ALL" | "MANDATORY" | "GAPS";

export function RequirementTable({
  requirements,
  selectedId,
  onSelect,
}: RequirementTableProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return requirements.filter((requirement) => {
      const matchesQuery =
        !normalized ||
        requirement.stable_key.toLowerCase().includes(normalized) ||
        requirement.text.toLowerCase().includes(normalized) ||
        requirement.requirement_type.toLowerCase().includes(normalized);
      const matchesFilter =
        filter === "ALL" ||
        (filter === "MANDATORY" && requirement.gate_type === "MANDATORY") ||
        (filter === "GAPS" && requirement.assessment !== "SATISFIED");
      return matchesQuery && matchesFilter;
    });
  }, [filter, query, requirements]);

  return (
    <div className="panel requirement-panel">
      <div className="panel-heading requirement-heading">
        <div>
          <span className="eyebrow">Obligation map</span>
          <h2>Requirement Control</h2>
        </div>
        <span className="tracked-count">
          <ShieldCheck size={15} /> {requirements.length} tracked
        </span>
      </div>
      <div className="table-toolbar">
        <label className="search-box">
          <Search size={15} />
          <input
            aria-label="Search requirements"
            placeholder="Search requirements"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="filter-tabs" aria-label="Requirement filters">
          {(["ALL", "MANDATORY", "GAPS"] as Filter[]).map((item) => (
            <button
              aria-pressed={filter === item}
              className={filter === item ? "active" : ""}
              key={item}
              onClick={() => setFilter(item)}
            >
              {item === "ALL" ? "All" : item === "MANDATORY" ? "Mandatory" : "Gaps"}
            </button>
          ))}
        </div>
      </div>
      <div className="table-scroll">
        <table className="requirement-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Requirement</th>
              <th>Gate</th>
              <th>Assessment</th>
              <th>Evidence</th>
              <th>Source</th>
              <th aria-label="Open" />
            </tr>
          </thead>
          <tbody>
            {filtered.map((requirement) => (
              <tr
                key={requirement.id}
                className={`${selectedId === requirement.id ? "selected" : ""} ${
                  requirement.assessment !== "SATISFIED" ? "has-gap" : ""
                }`}
                aria-selected={selectedId === requirement.id}
                onClick={() => onSelect(requirement)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(requirement);
                  }
                }}
                tabIndex={0}
              >
                <td>
                  <span className="requirement-id">{requirement.stable_key}</span>
                  {requirement.version > 1 && <span className="version-dot">v{requirement.version}</span>}
                </td>
                <td>
                  <span className="requirement-copy">{requirement.text}</span>
                  <small>{requirement.requirement_type}</small>
                </td>
                <td>
                  <StatusPill status={requirement.gate_type} compact />
                </td>
                <td>
                  <StatusPill status={requirement.assessment} />
                </td>
                <td>
                  <span className="evidence-count">
                    <strong>{requirement.evidence_count}</strong> verified
                  </span>
                </td>
                <td>
                  <span className="source-cell">
                    {requirement.source.document.includes("Technical")
                      ? "Tech Spec"
                      : requirement.source.document.includes("Corrigendum")
                        ? "Corrigendum #2"
                        : "Main Tender"}
                    <small>p.{requirement.source.page}</small>
                  </span>
                </td>
                <td>
                  <ChevronRight size={16} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length === 0 && <div className="empty-table">No requirements match this view.</div>}
    </div>
  );
}
