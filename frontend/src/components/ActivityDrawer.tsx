import { Activity, Bot, ChevronRight, X } from "lucide-react";
import type { ActivityEvent } from "../types/bid";

function eventLabel(eventType: string) {
  return eventType
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-SG", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Singapore",
    hour12: false,
  }).format(new Date(value.endsWith("Z") ? value : `${value}Z`));
}

interface ActivityDrawerProps {
  open: boolean;
  onClose: () => void;
  events: ActivityEvent[];
}

export function ActivityDrawer({ open, onClose, events }: ActivityDrawerProps) {
  return (
    <>
      <button
        aria-label="Close activity drawer"
        className={`drawer-backdrop ${open ? "open" : ""}`}
        onClick={onClose}
      />
      <aside className={`activity-drawer ${open ? "open" : ""}`} aria-hidden={!open}>
        <div className="drawer-header">
          <div>
            <span className="eyebrow">Structured observability</span>
            <h2>Agent Activity</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close">
            <X size={19} />
          </button>
        </div>
        <div className="drawer-note">
          <Bot size={17} />
          <p>Action and decision summaries only. No hidden reasoning is exposed.</p>
        </div>
        <div className="activity-timeline">
          {events.map((event, index) => (
            <article key={event.id} className="activity-event">
              <div className="activity-rail">
                <span className={index < 3 ? "recent" : ""}>
                  <Activity size={11} />
                </span>
              </div>
              <time>{formatTime(event.timestamp)}</time>
              <div>
                <span className="activity-type">{eventLabel(event.event_type)}</span>
                <p>{event.summary}</p>
                {event.entity_id && (
                  <small>
                    {event.entity_id} <ChevronRight size={11} />
                  </small>
                )}
              </div>
            </article>
          ))}
        </div>
      </aside>
    </>
  );
}
