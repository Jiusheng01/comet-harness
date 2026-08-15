import { lazy, Suspense } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
const HomePage = lazy(() => import('./pages/HomePage'))
const LoginPage = lazy(() => import('./pages/LoginPage'))
const ModelConfigPage = lazy(() => import('./pages/ModelConfigPage'))
const KnowledgeBasePage = lazy(() => import('./pages/KnowledgeBasePage'))
const KnowledgeDetailPage = lazy(() => import('./pages/KnowledgeDetailPage'))
const ImagePage = lazy(() => import('./pages/ImagePage'))
const MemoryPage = lazy(() => import('./pages/MemoryPage'))
const GraphPage = lazy(() => import('./pages/GraphPage'))
const ChatPage = lazy(() => import('./pages/ChatPage'))
const ResearchPage = lazy(() => import('./pages/ResearchPage'))
const AgentTaskPage = lazy(() => import('./pages/AgentTaskPage'))
const NotifyChannelPage = lazy(() => import('./pages/NotifyChannelPage'))
const AgentConfigPage = lazy(() => import('./pages/AgentConfigPage'))
const SkillPage = lazy(() => import('./pages/SkillPage'))
const ToolConfigPage = lazy(() => import('./pages/ToolConfigPage'))
const SearchPage = lazy(() => import('./pages/SearchPage'))
const ProfilePage = lazy(() => import('./pages/ProfilePage'))
const SharePage = lazy(() => import('./pages/SharePage'))
const ReportSharePage = lazy(() => import('./pages/ReportSharePage'))
const TracesPage = lazy(() => import('./pages/TracesPage'))
import RequireAuth from './components/RequireAuth'
import ErrorBoundary from './components/ErrorBoundary'

// 阶段1：登录页 + 路由守卫；主布局需登录后访问
export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Suspense fallback={null}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/s/:token" element={<SharePage />} />
          <Route path="/r/:token" element={<ReportSharePage />} />
          <Route
            path="/"
            element={
              <RequireAuth>
                <MainLayout />
              </RequireAuth>
            }
          >
            <Route index element={<HomePage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="research" element={<ResearchPage />} />
            <Route path="agent-tasks" element={<AgentTaskPage />} />
            <Route path="knowledge" element={<KnowledgeBasePage />} />
            <Route path="knowledge-bases/:kbId" element={<KnowledgeDetailPage />} />
            <Route path="images" element={<ImagePage />} />
            <Route path="memory" element={<MemoryPage />} />
            <Route path="graph" element={<GraphPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="traces" element={<TracesPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="settings/models" element={<ModelConfigPage />} />
            <Route path="settings/agent" element={<AgentConfigPage />} />
            <Route path="settings/skills" element={<SkillPage />} />
            <Route path="settings/tools" element={<ToolConfigPage />} />
            <Route path="settings/notify" element={<NotifyChannelPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
