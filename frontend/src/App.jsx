import { Navigate, Route, Routes } from "react-router-dom";
import { AppProvider } from "./context.jsx";
import Layout from "./components/Layout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Meetings from "./pages/Meetings.jsx";
import MeetingDetail from "./pages/MeetingDetail.jsx";
import Tasks from "./pages/Tasks.jsx";
import Calendar from "./pages/Calendar.jsx";
import Team from "./pages/Team.jsx";
import ChatPage from "./pages/ChatPage.jsx";

export default function App() {
  return (
    <AppProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/meetings" element={<Meetings />} />
          <Route path="/meetings/:id" element={<MeetingDetail />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/team" element={<Team />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </AppProvider>
  );
}
