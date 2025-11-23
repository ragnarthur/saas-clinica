// src/layout/BaseLayout.tsx
import React, { useEffect, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { apiRequest } from "../api/client";
import { useAuth } from "../auth/useAuth";
import type { MeDTO } from "../types";
import { APP_NAME } from "../config/appConfig"; // <<< NOVO

import "../styles/layout.css";

type Role = "CLINIC_OWNER" | "DOCTOR" | "SECRETARY" | "SAAS_ADMIN";

type NavItem = {
  to: string;
  label: string;
  roles: Role[];
};

type BaseLayoutProps = {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
};

const NAV_ITEMS: NavItem[] = [
  {
    to: "/dashboard",
    label: "Agenda",
    roles: ["CLINIC_OWNER", "DOCTOR", "SECRETARY", "SAAS_ADMIN"],
  },
  {
    to: "/patients",
    label: "Pacientes",
    roles: ["CLINIC_OWNER", "DOCTOR", "SECRETARY", "SAAS_ADMIN"],
  },
  {
    to: "/staff",
    label: "Equipe",
    roles: ["CLINIC_OWNER", "SAAS_ADMIN"],
  },
  {
    to: "/consentimentos",
    label: "Consentimentos",
    roles: ["CLINIC_OWNER", "SAAS_ADMIN"],
  },
];

const BaseLayout: React.FC<BaseLayoutProps> = ({
  children,
  title,
  subtitle,
}) => {
  const { logout } = useAuth();
  const [me, setMe] = useState<MeDTO | null>(null);
  const [loadingMe, setLoadingMe] = useState<boolean>(true);

  const navigate = useNavigate();

  // título da aba do navegador (para telas autenticadas)
  useEffect(() => {
    const pageTitle = title ? `${title} · ${APP_NAME}` : APP_NAME;
    document.title = pageTitle;
  }, [title]);

  useEffect(() => {
    let active = true;

    async function loadMe() {
      try {
        setLoadingMe(true);
        const data = await apiRequest<MeDTO>("/auth/me/", { method: "GET" });
        if (!active) return;
        setMe(data);
      } catch (error) {
        console.error("[BASE LAYOUT] Erro ao carregar /auth/me/:", error);
      } finally {
        if (active) {
          setLoadingMe(false);
        }
      }
    }

    loadMe();

    return () => {
      active = false;
    };
  }, []);

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function canSeeNav(item: NavItem): boolean {
    const role = me?.role as Role | undefined;
    if (!role) return false;
    return item.roles.includes(role);
  }

  const displayName = me
    ? `${me.first_name || me.username}${
        me.last_name ? ` ${me.last_name}` : ""
      }`
    : "";

  const clinicName = me?.clinic?.name ?? null;

  const computedSubtitle =
    subtitle ??
    (me
      ? [
          `Logado como ${displayName}`,
          clinicName ? `Clínica ${clinicName}` : null,
        ]
          .filter(Boolean)
          .join(" · ")
      : "");

  const pageTitle = title ?? "Painel";

  const buildNavClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "app-nav-link app-nav-link--active" : "app-nav-link";

  return (
    <div className="app-shell">
      {/* NAVBAR / HEADER */}
      <header className="app-header">
        {/* Branding */}
        <button
          type="button"
          className="app-brand"
          onClick={() => navigate("/dashboard")}
        >
          <span className="app-brand-pill">{APP_NAME}</span>
        </button>

        {/* Links de navegação */}
        <nav className="app-nav" aria-label="Navegação principal">
          {NAV_ITEMS.filter(canSeeNav).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={buildNavClass}
              end={item.to === "/dashboard"}
            >
              <span>{item.label}</span>
              <span className="app-nav-underline" />
            </NavLink>
          ))}
        </nav>

        {/* Meta do usuário + botão sair */}
        <div className="app-header-right">
          {!loadingMe && me && (
            <div className="app-user-meta">
              <span className="app-user-name">{displayName}</span>
              {clinicName && (
                <>
                  <span>·</span>
                  <span className="app-user-clinic">{clinicName}</span>
                </>
              )}
            </div>
          )}

          <button
            type="button"
            className="app-logout-button"
            onClick={handleLogout}
          >
            Sair
          </button>
        </div>
      </header>

      {/* CONTEÚDO */}
      <main className="app-main">
        <div className="app-main-inner">
          <div className="page-header">
            <h1 className="page-title">{pageTitle}</h1>
            {computedSubtitle && (
              <p className="page-subtitle">{computedSubtitle}</p>
            )}
          </div>

          {children}
        </div>
      </main>
    </div>
  );
};

export default BaseLayout;
