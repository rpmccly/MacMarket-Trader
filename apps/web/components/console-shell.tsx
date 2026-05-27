"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { ThemeToggle } from "@/components/theme-toggle";
import { BrandLockup } from "@/components/brand-lockup";
import { TopbarContext } from "@/components/topbar-context";
import { ActiveTradeBanner } from "@/components/active-trade-banner";
import { isActivePath } from "@/lib/console-nav";

const navSections = [
  {
    title: "Workflow",
    links: [
      ["/dashboard", "Dashboard"],
      ["/analysis", "Analyze"],
      ["/recommendations", "Recommendation"],
      ["/replay-runs", "Replay"],
      ["/orders", "Paper Order"],
    ],
  },
  {
    title: "Research",
    links: [
      ["/analyze", "Symbol Snapshot"],
      ["/charts/haco", "HACO Context"],
      ["/momentum-heatmap", "Momentum Heatmap"],
      ["/haco-heatmap", "HACO Direction Heatmap"],
      ["/charts/momentum", "Momentum Intelligence"],
    ],
  },
  {
    title: "Reports",
    links: [["/schedules", "Scheduled Reports"]],
  },
  {
    title: "Help",
    links: [["/welcome", "Welcome guide"]],
  },
  {
    title: "Preferences",
    links: [["/settings", "Settings"]],
  },
  {
    title: "Admin",
    links: [
      ["/admin/pending-users", "Admin / Invites"],
      ["/admin/users", "Admin / Users"],
      ["/admin/provider-health", "Provider Health"],
      ["/account", "Account"],
    ],
  },
] as const;

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const buildStamp = process.env.NEXT_PUBLIC_BUILD_STAMP ?? "dev-local";
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const [appRole, setAppRole] = useState<string | null>(null);
  const [meChecked, setMeChecked] = useState(false);

  useEffect(() => {
    fetch("/api/user/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { app_role?: string } | null) => {
        setAppRole(data?.app_role ? String(data.app_role) : null);
        setMeChecked(true);
      })
      .catch(() => {
        setAppRole(null);
        setMeChecked(true);
      });
  }, []);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    closeButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [drawerOpen]);

  const isAdmin = meChecked && appRole === "admin";

  const nav = (
    <nav className="op-nav" aria-label="Operator console">
      {navSections.map((section) => {
        if (section.title === "Admin" && !isAdmin) return null;
        return (
          <section key={section.title} className="op-nav-section">
            <div className="op-nav-section-title">{section.title}</div>
            <div className="op-nav-links">
              {section.links.map(([href, label]) => {
                const active = isActivePath(pathname, href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={active ? "is-active" : ""}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setDrawerOpen(false)}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })}
    </nav>
  );

  return (
    <div className={`op-shell ${drawerOpen ? "is-drawer-open" : ""}`}>
      <button
        type="button"
        className="op-drawer-backdrop"
        aria-label="Close navigation menu"
        onClick={() => setDrawerOpen(false)}
      />
      <aside className="op-aside" id="console-navigation" aria-label="Console navigation">
        <button
          ref={closeButtonRef}
          type="button"
          className="op-drawer-close"
          aria-label="Close navigation menu"
          onClick={() => setDrawerOpen(false)}
        >
          Close
        </button>
        <div className="op-brand-block">
          <BrandLockup />
          <p className="op-brand-caption">Invite-only private alpha console</p>
        </div>
        {nav}
      </aside>
      <section className="op-main">
        <ActiveTradeBanner />
        <header className="op-topbar">
          <div className="op-topbar-brand">
            <button
              type="button"
              className="op-mobile-menu-button"
              aria-label="Open navigation menu"
              aria-controls="console-navigation"
              aria-expanded={drawerOpen}
              data-testid="mobile-nav-toggle"
              onClick={() => setDrawerOpen(true)}
            >
              Menu
            </button>
            <BrandLockup compact />
            <TopbarContext />
          </div>
          <div className="op-topbar-actions">
            <span className="op-build-stamp">build: {buildStamp}</span>
            <ThemeToggle />
          </div>
        </header>
        <main className="op-content">{children}</main>
      </section>
    </div>
  );
}
