import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Hospitals from './pages/Hospitals';
import Onboarding from './pages/Onboarding';
import './index.css';
import './App.css';

function AppLayout({ children }) {
  return (
    <div className="app-layout">
      <Sidebar />
      <main className="app-main">
        {children}
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={<AppLayout><Dashboard /></AppLayout>}
        />
        <Route
          path="/hospitals"
          element={<AppLayout><Hospitals /></AppLayout>}
        />
        <Route
          path="/onboarding"
          element={<AppLayout><Onboarding /></AppLayout>}
        />
      </Routes>
    </BrowserRouter>
  );
}
