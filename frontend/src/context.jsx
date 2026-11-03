import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

const AppContext = createContext(null);

const THEME_KEY = "meetwise-theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function readStoredTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "system";
  } catch {
    return "system";
  }
}

/*
 * App-wide state: the people directory (the current user is the person flagged is_user),
 * the assistant panel, and toast notifications.
 */
export function AppProvider({ children }) {
  const [people, setPeople] = useState([]);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantScope, setAssistantScope] = useState({ type: "all", meetingId: null, meetingTitle: null });
  const [toast, setToast] = useState(null);
  const [themePreference, setThemePreference] = useState(readStoredTheme);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.(DARK_QUERY).matches ?? false);

  // Follow the operating system while the preference is "system".
  useEffect(() => {
    const query = window.matchMedia?.(DARK_QUERY);
    if (!query) return undefined;
    const onChange = (event) => setSystemDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const resolvedTheme = themePreference === "system" ? (systemDark ? "dark" : "light") : themePreference;

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
  }, [resolvedTheme]);

  const chooseTheme = useCallback((preference) => {
    try {
      localStorage.setItem(THEME_KEY, preference);
    } catch {
      /* storage unavailable: the choice lasts for this session only */
    }
    setThemePreference(preference);
  }, []);

  const loadPeople = useCallback(async () => {
    try {
      setPeople(await api.people.list());
    } catch {
      /* the team page shows its own error; the shell stays usable */
    }
  }, []);

  useEffect(() => {
    loadPeople();
  }, [loadPeople]);

  const notify = useCallback((message, tone = "ok") => {
    setToast({ message, tone, id: Date.now() });
    window.clearTimeout(notify.timer);
    notify.timer = window.setTimeout(() => setToast(null), 3200);
  }, []);

  const openAssistant = useCallback((scope = { type: "all" }) => {
    setAssistantScope({ type: "all", meetingId: null, meetingTitle: null, ...scope });
    setAssistantOpen(true);
  }, []);

  const value = {
    people,
    me: people.find((p) => p.is_user) || null,
    loadPeople,
    assistantOpen,
    setAssistantOpen,
    assistantScope,
    openAssistant,
    notify,
    toast,
    themePreference,
    resolvedTheme,
    chooseTheme,
  };
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside AppProvider");
  return value;
}
