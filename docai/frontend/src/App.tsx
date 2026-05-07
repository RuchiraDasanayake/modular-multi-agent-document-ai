import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import { AppLayout } from "./components/layout/AppLayout";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDashboardPage from "./pages/ProjectDashboardPage";
import SchemaBuilderPage from "./pages/SchemaBuilderPage";
import JobsPage from "./pages/JobsPage";
import NewJobPage from "./pages/NewJobPage";
import JobViewerPage from "./pages/JobViewerPage";
import DocumentReviewPage from "./pages/DocumentReviewPage";
import MetricsPage from "./pages/MetricsPage";

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/run" element={<Navigate to="/" replace />} />
          <Route path="/projects/:id" element={<ProjectDashboardPage />} />
          <Route path="/projects/:id/schema" element={<SchemaBuilderPage />} />
          <Route path="/projects/:id/jobs" element={<JobsPage />} />
          <Route path="/projects/:id/jobs/new" element={<NewJobPage />} />
          <Route path="/projects/:project_id/jobs/:job_id" element={<JobViewerPage />} />
          <Route path="/projects/:project_id/jobs/:job_id/document/:doc_id" element={<DocumentReviewPage />} />
          <Route path="/projects/:id/metrics" element={<MetricsPage />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}
