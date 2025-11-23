// src/App.tsx
import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import PatientSignupPage from "./pages/PatientSignupPage";
import PatientsPage from "./pages/PatientsPage";
import StaffPage from "./pages/StaffPage";
import ConsentPage from "./pages/ConsentPage";
import PrivateRoute from "./routes/PrivateRoute";
import BaseLayout from "./layout/BaseLayout";

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        {/* públicas */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/cadastro-paciente" element={<PatientSignupPage />} />

        {/* protegidas */}
        <Route
          path="/dashboard"
          element={
            <PrivateRoute>
              <BaseLayout title="Painel">
                <DashboardPage />
              </BaseLayout>
            </PrivateRoute>
          }
        />

        <Route
          path="/patients"
          element={
            <PrivateRoute>
              <BaseLayout title="Pacientes">
                <PatientsPage />
              </BaseLayout>
            </PrivateRoute>
          }
        />

        <Route
          path="/staff"
          element={
            <PrivateRoute>
              <BaseLayout title="Equipe">
                <StaffPage />
              </BaseLayout>
            </PrivateRoute>
          }
        />

        <Route
          path="/consentimentos"
          element={
            <PrivateRoute>
              <BaseLayout title="Consentimentos">
                <ConsentPage />
              </BaseLayout>
            </PrivateRoute>
          }
        />

        {/* redirecionamentos padrão */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
