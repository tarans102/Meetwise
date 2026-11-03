import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Bell, CalendarDays, CheckSquare, Command, FileText, LayoutDashboard,
  MessageCircle, Monitor, Moon, Search, Sun, Users,
} from "lucide-react";
import { api } from "../api.js";
import { useApp } from "../context.jsx";
import { deadlineState, dueLabel, initials } from "../format.js";
import Assistant from "./Assistant.jsx";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/meetings", label: "Meetings", icon: FileText },
  { to: "/tasks", label: "My Tasks", icon: CheckSquare },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/team", label: "Team", icon: Users },
  { to: "/chat", label: "AI Chat", icon: MessageCircle },
];

export default function Layout({ children }) {
  const { me, toast, openAssistant } = useApp();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onKey = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="wordmark">Meet<span>Wise</span></div>
        <nav className="nav" aria-label="Main">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              <item.icon size={18} strokeWidth={1.7} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <NavLink to="/team" className="profile-chip">
            <span className="avatar">{initials(me?.name)}</span>
            <span className="small">
              <strong>{me?.name || "Set up your profile"}</strong>
              <br />
              <span className="muted">{me?.designation || "Profile & settings"}</span>
            </span>
          </NavLink>
        </div>
      </aside>

      <div className="main">
        <Topbar onOpenPalette={() => setPaletteOpen(true)} />
        <main>{children}</main>
      </div>

      <nav className="bottom-nav" aria-label="Main">
        {NAV.slice(0, 5).map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}>
            <item.icon size={20} strokeWidth={1.7} />
            {item.label.replace("My ", "")}
          </NavLink>
        ))}
      </nav>

      <Assistant mode="panel" />
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} onAsk={openAssistant} />}
      {toast && <div className={`toast ${toast.tone === "error" ? "toast-error" : ""}`} role="status">{toast.message}</div>}
    </div>
  );
}

function Topbar({ onOpenPalette }) {
  return (
    <header className="topbar">
      <GlobalSearch />
      <div className="topbar-actions">
        <button className="icon-btn" onClick={onOpenPalette} aria-label="Command palette (Ctrl+K)" title="Ctrl+K">
          <Command size={18} />
        </button>
        <ThemeToggle />
        <Notifications />
      </div>
    </header>
  );
}

const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };
const THEME_NEXT = { system: "light", light: "dark", dark: "system" };

function ThemeToggle() {
  const { themePreference, chooseTheme } = useApp();
  const Icon = THEME_ICON[themePreference] || Monitor;
  const label = `Theme: ${themePreference}. Switch to ${THEME_NEXT[themePreference]}.`;
  return (
    <button className="icon-btn" aria-label={label} title={label} onClick={() => chooseTheme(THEME_NEXT[themePreference])}>
      <Icon size={18} />
    </button>
  );
}

function GlobalSearch() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState({ meetings: [], transcript: [] });
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults({ meetings: [], transcript: [] });
      return undefined;
    }
    const timer = setTimeout(async () => {
      try {
        const [meetings, transcript] = await Promise.all([
          api.meetings.list(),
          api.search({ query: trimmed, k: 5 }),
        ]);
        const q = trimmed.toLowerCase();
        setResults({
          meetings: meetings.filter((m) => (m.title || "").toLowerCase().includes(q)).slice(0, 5),
          transcript,
        });
      } catch {
        setResults({ meetings: [], transcript: [] });
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    const onDown = (event) => wrapRef.current && !wrapRef.current.contains(event.target) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const go = (path) => {
    setOpen(false);
    setQuery("");
    navigate(path);
  };
  const hasResults = results.meetings.length || results.transcript.length;

  return (
    <div className="search" ref={wrapRef}>
      <Search size={16} className="search-icon" />
      <input
        className="input"
        placeholder="Search meetings and transcripts"
        aria-label="Global search"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {open && query.trim().length >= 2 && (
        <div className="popover" style={{ left: 0, right: "auto", width: "100%" }}>
          {!hasResults && <p className="muted small" style={{ padding: 12 }}>No matches.</p>}
          {results.meetings.map((m) => (
            <button key={m.id} className="popover-item" onClick={() => go(`/meetings/${m.id}`)}>
              <strong>{m.title || "Untitled meeting"}</strong>
              <span className="mono" style={{ display: "block" }}>Meeting</span>
            </button>
          ))}
          {results.transcript.map((hit) => (
            <button key={hit.chunk_id} className="popover-item" onClick={() => go(hit.metadata.task_id ? "/tasks" : `/meetings/${hit.metadata.meeting_id}`)}>
              <span className="small">{hit.text.slice(0, 120)}{hit.text.length > 120 ? "…" : ""}</span>
              <span className="mono" style={{ display: "block" }}>{hit.metadata.meeting_title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Notifications() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const ref = useRef(null);

  const load = useCallback(async () => {
    try {
      const [tasks, pending] = await Promise.all([api.tasks.list({ category: "direct" }), api.events.pending()]);
      const next = [];
      tasks.filter((t) => t.status === "blocked").forEach((t) =>
        next.push({ id: `b-${t.id}`, text: `Blocked: ${t.description}`, to: "/tasks" }));
      tasks.forEach((t) => {
        const state = deadlineState(t);
        if (state === "overdue") next.push({ id: `o-${t.id}`, text: `Overdue (${dueLabel(t)}): ${t.description}`, to: "/tasks" });
        if (state === "today") next.push({ id: `d-${t.id}`, text: `Due today: ${t.description}`, to: "/tasks" });
      });
      if (pending.length) next.push({ id: "p", text: `${pending.length} suggested event${pending.length > 1 ? "s" : ""} to review`, to: "/calendar" });
      setItems(next);
    } catch {
      setItems([]);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  }, [load]);

  useEffect(() => {
    const onDown = (event) => ref.current && !ref.current.contains(event.target) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="icon-btn" aria-label="Notifications" onClick={() => setOpen((o) => !o)}>
        <Bell size={18} />
        {items.length > 0 && <span className="bell-dot" />}
      </button>
      {open && (
        <div className="popover">
          {items.length === 0 && <p className="muted small" style={{ padding: 12 }}>You're all caught up.</p>}
          {items.map((item) => (
            <button key={item.id} className="popover-item small" onClick={() => { setOpen(false); navigate(item.to); }}>
              {item.text}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CommandPalette({ onClose, onAsk }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [meetings, setMeetings] = useState([]);

  useEffect(() => {
    api.meetings.list().then(setMeetings).catch(() => setMeetings([]));
  }, []);

  const commands = useMemo(() => [
    ...NAV.map((n) => ({ label: `Go to ${n.label}`, run: () => navigate(n.to) })),
    { label: "Ask MeetWise", run: () => onAsk({ type: "all" }) },
    ...meetings.map((m) => ({ label: `Open meeting: ${m.title || "Untitled"}`, run: () => navigate(`/meetings/${m.id}`) })),
  ], [meetings, navigate, onAsk]);

  const filtered = commands.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()));

  const choose = (command) => {
    onClose();
    command.run();
  };

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ width: "min(560px, 100%)" }} role="dialog" aria-label="Command palette">
        <div className="modal-body" style={{ paddingTop: 16 }}>
          <input
            className="input"
            autoFocus
            placeholder="Type a command or meeting name"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && filtered[0]) choose(filtered[0]);
            }}
          />
        </div>
        <div className="modal-body" style={{ maxHeight: 360 }}>
          {filtered.slice(0, 12).map((c) => (
            <button key={c.label} className="popover-item" style={{ position: "relative", display: "block", background: "none" }} onClick={() => choose(c)}>
              {c.label}
            </button>
          ))}
          {filtered.length === 0 && <p className="muted small">Nothing matches "{query}".</p>}
        </div>
      </div>
    </div>
  );
}
