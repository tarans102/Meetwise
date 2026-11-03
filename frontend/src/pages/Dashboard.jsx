import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { Badge, Button, Empty, Spinner } from "../components/ui.jsx";
import { STAGE_LABEL, TASK_STATUS, dayKey, deadlineState, dueLabel, formatDate, formatTime, greeting, truncate } from "../format.js";

export default function Dashboard() {
  const { me, openAssistant } = useApp();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const today = new Date();
    const next = new Date(today);
    next.setDate(today.getDate() + 14);
    Promise.all([
      api.meetings.list(),
      api.tasks.list(),
      api.events.range(dayKey(today), dayKey(next)),
      api.events.pending(),
    ])
      .then(([meetings, tasks, events, pending]) => setData({ meetings, tasks, events, pending }))
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <div className="page"><p className="error-text">Couldn't load the dashboard: {error}</p></div>;
  if (!data) return <div className="page"><Spinner /></div>;

  const weekAgo = new Date();
  weekAgo.setDate(weekAgo.getDate() - 7);
  const meetingsThisWeek = data.meetings.filter((m) => new Date(m.meeting_date || m.created_at) >= weekAgo).length;
  const mine = data.tasks.filter((t) => t.category === "direct");
  const openMine = mine.filter((t) => t.status !== "completed");
  const completedMine = mine.filter((t) => t.status === "completed");
  const deadlines = openMine.filter((t) => t.due_on || t.due_date);
  const priorities = [...openMine]
    .sort((a, b) => rank(a) - rank(b))
    .slice(0, 5);
  const blockedByOthers = data.tasks.filter((t) => t.status === "blocked" && t.category !== "direct");
  const upcomingEvents = data.events.slice(0, 5);
  const recent = data.meetings.slice(0, 4);

  return (
    <div className="page">
      <header className="page-head">
        <p className="mono">{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p>
        <h1 style={{ marginTop: 6 }}>{greeting()}{me ? `, ${me.name.split(" ")[0]}` : ""}.</h1>
        <p>
          {openMine.length
            ? `You have ${openMine.length} open ${openMine.length === 1 ? "commitment" : "commitments"}${blockedByOthers.length ? `, and ${blockedByOthers.length} blocked item${blockedByOthers.length > 1 ? "s" : ""} elsewhere` : ""}.`
            : "Nothing open on your plate right now."}
        </p>
      </header>

      <section className="row" style={{ gap: 12 }} aria-label="Weekly overview">
        <Stat label="Meetings this week" value={meetingsThisWeek} />
        <Stat label="Pending tasks" value={openMine.length} />
        <Stat label="Completed tasks" value={completedMine.length} />
        <Stat label="With deadlines" value={deadlines.length} />
      </section>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.6fr) minmax(0, 1fr)", gap: 24, marginTop: 32, alignItems: "start" }}>
        <div className="stack" style={{ gap: 24 }}>
          <section>
            <div className="spread" style={{ marginBottom: 12 }}>
              <h2 className="section-title" style={{ margin: 0 }}>Recent meetings</h2>
              <Link to="/meetings" className="small">All meetings →</Link>
            </div>
            {recent.length === 0 && (
              <Empty title="No meetings yet">Upload a transcript to get started.</Empty>
            )}
            <ul className="list card" style={{ padding: "0 20px" }}>
              {recent.map((m) => (
                <li key={m.id}>
                  <Link to={`/meetings/${m.id}`} style={{ textDecoration: "none" }}>
                    <div className="spread">
                      <h3>{m.title || "Untitled meeting"}</h3>
                      <StatusTag meeting={m} />
                    </div>
                    <div className="meta-line">
                      <span>{formatDate(m.meeting_date || m.created_at)}</span>
                      <span>{(m.participants || []).slice(0, 4).join(", ") || "No participants"}</span>
                      {m.status === "completed" && <span>{m.action_count} action {m.action_count === 1 ? "item" : "items"}</span>}
                    </div>
                    {m.executive_summary && (
                      <p className="small muted" style={{ marginTop: 8 }}>{truncate(m.executive_summary, 170)}</p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h2 className="section-title">My priorities</h2>
            {priorities.length === 0 ? (
              <Empty title="All clear">Your direct commitments will appear here.</Empty>
            ) : (
              <ul className="list card" style={{ padding: "0 20px" }}>
                {priorities.map((t) => (
                  <li key={t.id} className="spread">
                    <div>
                      <strong>{t.description}</strong>
                      <div className="meta-line">
                        {(t.due_on || t.due_date) && <span>Due {dueLabel(t)}</span>}
                        <span>{TASK_STATUS[t.status]}</span>
                      </div>
                    </div>
                    <div className="row" style={{ gap: 6 }}>
                      {deadlineState(t) === "overdue" && <Badge tone="danger">Overdue</Badge>}
                      {deadlineState(t) === "today" && <Badge tone="amber">Due today</Badge>}
                      {t.status === "blocked" && <Badge tone="danger">Blocked</Badge>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <div className="stack" style={{ gap: 24 }}>
          <section className="card">
            <div className="spread" style={{ marginBottom: 8 }}>
              <h3>Next two weeks</h3>
              <Link to="/calendar" className="small">Calendar →</Link>
            </div>
            {upcomingEvents.length === 0 && <p className="muted small">No confirmed events.</p>}
            <ul className="list">
              {upcomingEvents.map((e) => (
                <li key={e.id} style={{ padding: "10px 0" }}>
                  <div className="small"><strong>{e.title}</strong></div>
                  <div className="mono">{formatDate(e.starts_at)}{!e.all_day ? ` · ${formatTime(e.starts_at)}` : ""}</div>
                </li>
              ))}
            </ul>
            {data.pending.length > 0 && (
              <p className="notice" style={{ marginTop: 12 }}>
                {data.pending.length} suggested {data.pending.length === 1 ? "event" : "events"} waiting for your review.
              </p>
            )}
          </section>

          <section className="card">
            <h3>Ask MeetWise</h3>
            <p className="muted small" style={{ margin: "6px 0 12px" }}>
              Questions about decisions, commitments and past discussions, answered from your transcripts.
            </p>
            <div className="row">
              <Button variant="primary" size="sm" onClick={() => openAssistant({ type: "all" })}>Ask a question</Button>
              <Button size="sm" onClick={() => navigate("/chat")}>Open chat</Button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="card" style={{ padding: "14px 18px", minWidth: 150, flex: "1 1 150px" }}>
      <div className="mono">{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: 32, lineHeight: 1.1, marginTop: 4 }}>{value}</div>
    </div>
  );
}

export function StatusTag({ meeting }) {
  if (meeting.status === "error") return <Badge tone="danger">Failed</Badge>;
  if (meeting.status === "completed") return <Badge tone="completed">Ready</Badge>;
  return <Badge tone="amber">{STAGE_LABEL[meeting.stage] || "Processing"}</Badge>;
}

// Blocked first, then overdue, then due today, then other deadlines, then high priority.
function rank(task) {
  if (task.status === "blocked") return 0;
  const state = deadlineState(task);
  if (state === "overdue") return 1;
  if (state === "today") return 2;
  if (task.due_on || task.due_date) return 3;
  if (task.priority === "high") return 4;
  return 5;
}
