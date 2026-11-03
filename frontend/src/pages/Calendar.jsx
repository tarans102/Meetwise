import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, ChevronLeft, ChevronRight, Flag, Plus, Users, Trash2 } from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { Button, Field, Modal, Spinner } from "../components/ui.jsx";
import { EVENT_TYPE_LABEL, dayKey, formatTime } from "../format.js";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// Visual language: lavender for meetings, dusty rose for deadlines, amber for general
// events, sage once completed. Each also carries an icon and a text label.
const TYPE_STYLE = {
  meeting: { cls: "meeting", icon: Users },
  deadline: { cls: "deadline", icon: Flag },
  general: { cls: "general", icon: CalendarDays },
};

export default function Calendar() {
  const { notify } = useApp();
  const [cursor, setCursor] = useState(() => new Date());
  const [events, setEvents] = useState(null);
  const [pending, setPending] = useState([]);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(null);

  const days = useMemo(() => monthGrid(cursor), [cursor]);

  const load = useCallback(async () => {
    try {
      const [range, pend] = await Promise.all([
        api.events.range(dayKey(days[0]), dayKey(days[days.length - 1])),
        api.events.pending(),
      ]);
      setEvents(range);
      setPending(pend);
    } catch (err) {
      notify(err.message, "error");
    }
  }, [days, notify]);

  useEffect(() => {
    load();
  }, [load]);

  if (!events) return <div className="page"><Spinner /></div>;

  const today = dayKey(new Date());
  const byDay = {};
  events.forEach((e) => {
    const key = e.starts_at.slice(0, 10);
    (byDay[key] ||= []).push(e);
  });

  return (
    <div className="page">
      <header className="spread page-head">
        <div>
          <h1>Calendar</h1>
          <p>Stored in MeetWise only. Nothing is sent to an external calendar.</p>
        </div>
        <Button variant="primary" onClick={() => setCreating({ date: dayKey(cursor) })}><Plus size={15} /> New event</Button>
      </header>

      <div className="spread" style={{ marginBottom: 16 }}>
        <div className="row">
          <button className="icon-btn" aria-label="Previous month" onClick={() => setCursor(addMonths(cursor, -1))}><ChevronLeft size={18} /></button>
          <h2 style={{ fontSize: 22, minWidth: 200, textAlign: "center" }}>
            {cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
          </h2>
          <button className="icon-btn" aria-label="Next month" onClick={() => setCursor(addMonths(cursor, 1))}><ChevronRight size={18} /></button>
          <Button size="sm" onClick={() => setCursor(new Date())}>Today</Button>
        </div>
        <Legend />
      </div>

      <div className="cal-grid" role="grid" aria-label="Month view">
        {WEEKDAYS.map((d) => <div key={d} className="cal-dow">{d}</div>)}
        {days.map((day) => {
          const key = dayKey(day);
          const inMonth = day.getMonth() === cursor.getMonth();
          const dayEvents = byDay[key] || [];
          return (
            <div
              key={key}
              className={`cal-cell ${inMonth ? "" : "outside"} ${key === today ? "today" : ""}`}
              onDoubleClick={() => setCreating({ date: key })}
            >
              <span className="day-num">{day.getDate()}</span>
              {dayEvents.map((e) => {
                const style = TYPE_STYLE[e.event_type] || TYPE_STYLE.general;
                const kind = e.completed ? "completed" : style.cls;
                const Icon = e.completed ? Check : style.icon;
                return (
                  <button key={e.id} className={`event-chip ${kind}`} onClick={() => setSelected(e)} title={e.title}>
                    <Icon size={12} aria-hidden="true" />
                    {!e.all_day && <span className="mono" style={{ color: "inherit" }}>{formatTime(e.starts_at)}</span>}
                    <span>{e.title}</span>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>

      {pending.length > 0 && (
        <section className="section">
          <h2 className="section-title">Suggested from meetings</h2>
          <p className="muted small" style={{ marginBottom: 12 }}>
            Found in transcripts. Confirm to place on the calendar, or dismiss. Dates you need to fix can be edited first.
          </p>
          <PendingReview items={pending} onChanged={load} notify={notify} />
        </section>
      )}

      {selected && <EventDialog event={selected} onClose={() => setSelected(null)} onChanged={() => { setSelected(null); load(); }} notify={notify} />}
      {creating && <NewEventDialog initialDate={creating.date} onClose={() => setCreating(null)} onCreated={() => { setCreating(null); load(); }} notify={notify} />}
    </div>
  );
}

function Legend() {
  return (
    <div className="legend" aria-label="Legend">
      <span><i style={{ background: "var(--color-meeting)" }} /><Users size={12} /> Meeting</span>
      <span><i style={{ background: "var(--color-deadline)" }} /><Flag size={12} /> Deadline</span>
      <span><i style={{ background: "var(--color-amber-soft)" }} /><CalendarDays size={12} /> Event</span>
      <span><i style={{ background: "var(--color-completed)" }} /><Check size={12} /> Completed</span>
    </div>
  );
}

function PendingReview({ items, onChanged, notify }) {
  const [drafts, setDrafts] = useState({});
  const [busy, setBusy] = useState(null);

  const confirm = async (event) => {
    setBusy(event.id);
    const draft = drafts[event.id] || {};
    const body = {};
    if (draft.starts_at) body.starts_at = draft.starts_at;
    if (draft.title) body.title = draft.title;
    try {
      await api.events.confirm(event.id, body);
      notify(`Added "${draft.title || event.title}"`);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(null);
    }
  };
  const dismiss = async (event) => {
    setBusy(event.id);
    try {
      await api.events.remove(event.id);
      onChanged();
    } catch (err) {
      notify(err.message, "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <ul className="list card" style={{ padding: "0 20px" }}>
      {items.map((e) => (
        <li key={e.id} className="grid-form" style={{ gridTemplateColumns: "minmax(0,1fr) 200px auto", alignItems: "end" }}>
          <div>
            <strong>{e.title}</strong>
            <div className="meta-line">
              <span>{EVENT_TYPE_LABEL[e.event_type]}</span>
              <span>{e.date_text ? `Mentioned as "${e.date_text}"` : "No date stated"}</span>
            </div>
          </div>
          <Field label={e.starts_at ? "Date and time" : "Set a date and time"}>
            <input
              type="datetime-local"
              className="input"
              defaultValue={e.starts_at && !e.all_day ? e.starts_at.slice(0, 16) : ""}
              onChange={(ev) => setDrafts((d) => ({ ...d, [e.id]: { ...d[e.id], starts_at: ev.target.value } }))}
            />
          </Field>
          <div className="row">
            <Button variant="primary" size="sm" disabled={busy === e.id || (!e.starts_at && !drafts[e.id]?.starts_at)} onClick={() => confirm(e)}>Confirm</Button>
            <Button variant="danger" size="sm" disabled={busy === e.id} onClick={() => dismiss(e)}><Trash2 size={13} /></Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function EventDialog({ event, onClose, onChanged, notify }) {
  const [busy, setBusy] = useState(false);
  const toggleComplete = async () => {
    setBusy(true);
    try {
      await api.events.update(event.id, { completed: !event.completed });
      onChanged();
    } catch (err) {
      notify(err.message, "error");
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    try {
      await api.events.remove(event.id);
      notify("Event deleted");
      onChanged();
    } catch (err) {
      notify(err.message, "error");
      setBusy(false);
    }
  };
  return (
    <Modal
      title={event.title}
      onClose={onClose}
      footer={
        <>
          <Button variant="danger" onClick={remove} disabled={busy}><Trash2 size={14} /> Delete</Button>
          <Button onClick={toggleComplete} disabled={busy}>{event.completed ? "Mark as not done" : "Mark completed"}</Button>
        </>
      }
    >
      <div className="stack">
        <p>{EVENT_TYPE_LABEL[event.event_type]} · {new Date(event.starts_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: event.all_day ? undefined : "short" })}</p>
        {event.location && <p className="muted">Location: {event.location}</p>}
        {event.participants?.length > 0 && <p className="muted">With: {event.participants.join(", ")}</p>}
        {event.notes && <p className="muted small">{event.notes}</p>}
      </div>
    </Modal>
  );
}

function NewEventDialog({ initialDate, onClose, onCreated, notify }) {
  const [form, setForm] = useState({ title: "", date: initialDate, start: "09:00", end: "10:00", event_type: "general", location: "" });
  const [busy, setBusy] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async () => {
    setBusy(true);
    try {
      await api.events.create({
        title: form.title.trim(),
        starts_at: form.start ? `${form.date}T${form.start}` : form.date,
        ends_at: form.end ? `${form.date}T${form.end}` : null,
        all_day: !form.start,
        event_type: form.event_type,
        location: form.location.trim() || null,
      });
      notify("Event added");
      onCreated();
    } catch (err) {
      notify(err.message, "error");
      setBusy(false);
    }
  };

  return (
    <Modal
      title="New event"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={submit} disabled={busy || !form.title.trim() || !form.date}>Save event</Button>
        </>
      }
    >
      <div className="grid-form">
        <Field label="Title" className="span-2"><input className="input" value={form.title} onChange={set("title")} autoFocus /></Field>
        <Field label="Date"><input type="date" className="input" value={form.date} onChange={set("date")} /></Field>
        <Field label="Type">
          <select className="select" value={form.event_type} onChange={set("event_type")}>
            {Object.entries(EVENT_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
        <Field label="Start"><input type="time" className="input" value={form.start} onChange={set("start")} /></Field>
        <Field label="End"><input type="time" className="input" value={form.end} onChange={set("end")} /></Field>
        <Field label="Location (optional)" className="span-2"><input className="input" value={form.location} onChange={set("location")} /></Field>
      </div>
    </Modal>
  );
}

function monthGrid(cursor) {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7; // Monday-first
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    return d;
  });
}

function addMonths(date, n) {
  return new Date(date.getFullYear(), date.getMonth() + n, 1);
}
