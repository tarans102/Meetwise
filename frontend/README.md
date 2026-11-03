# MeetWise Frontend

React + Vite single-page app for the MeetWise backend.

## Run

```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://localhost:8000
```

Start the backend first (`uvicorn meetwise.api.main:app --reload` from the backend folder).
For a production build: `npm run build`, then serve `dist/` behind the same origin as `/api`.

## Structure

```
src/
  styles/tokens.css   design tokens: colours, type, radii, shadows, spacing, motion
  styles/base.css     components and layout, written only in terms of tokens
  api.js              one function per backend endpoint
  format.js           labels and formatting (status, category, verdict wording, dates)
  context.jsx         people directory, assistant panel state, toasts
  components/
    Layout.jsx        sidebar, topbar (search, notifications), command palette (Ctrl+K), bottom nav on mobile
    Assistant.jsx     right-side panel from any page, and the AI Chat page; scope always shown
    ui.jsx            buttons, modals, confirm dialog, tabs, badges
  pages/              Dashboard, Meetings, MeetingDetail, Tasks, Calendar, Team, ChatPage
```

## Theme

The app supports three modes: follow the system (default), light, or dark. The switch is the sun/moon
icon in the topbar, and the choice is remembered in `localStorage`. `index.html` applies the theme before
the first paint, so there is no flash on load.

Colours are defined twice in `src/styles/tokens.css`: once for `[data-theme="light"]` and once for
`[data-theme="dark"]`. Components only reference the variables, so a new theme is a token change.

## Design system

All visual values live in `src/styles/tokens.css`. Change a colour or radius there and the whole app
follows. The light theme is the only one defined. A dark theme can be added by redefining the same
variables under `[data-theme="dark"]`.

Event colours follow the spec: lavender for meetings, dusty rose for deadlines, amber for general events, sage
for completed. Each also carries an icon and a text label.

## Backend contract

All endpoints listed in `src/api.js` are implemented by the backend. The transcript tab reads
`GET /api/meetings/{id}/transcript`, the meeting list includes `executive_summary`, and tasks include
`due_on` (a calendar date resolved against the meeting date). The UI shows `due_on` when present and
falls back to the wording used in the transcript otherwise.

## Notes

- Citations from the assistant link to `/meetings/{id}#U012`. The transcript tab opens and highlights that line.
- Extracted calendar events stay in "Suggested" until confirmed, following the backend rule.
- Destructive actions (removing a team member, dismissing an event) ask for confirmation first.
- Notifications are derived in the browser from tasks (overdue, due today, blocked) and pending events. They refresh every minute.
