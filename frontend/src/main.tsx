// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";

//  Global
import "./index.css";

//  Layout (navbar / shell)
import "./styles/layout.css";

//  Páginas / módulos
import "./styles/dashboard.css";
import "./styles/auth.css";
import "./styles/patient-signup.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
);
