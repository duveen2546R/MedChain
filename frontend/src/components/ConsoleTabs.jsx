import { NavLink } from "react-router-dom";
import Icon from "./Icon";
import { useAuth } from "../lib/auth";

const TABS = [
  { to: "/dashboard", label: "Dashboard", icon: "pulse", roles: null },
  { to: "/diagnosis", label: "Diagnosis", icon: "brain", roles: ["clinic_user", "platform_admin"] },
  { to: "/explorer", label: "Chain Explorer", icon: "chain", roles: ["platform_admin", "auditor", "research_partner"] },
  { to: "/audit", label: "Audit Log", icon: "shield", roles: ["platform_admin", "auditor"] },
];

/* Section switcher shared by every authenticated console page. */
export default function ConsoleTabs() {
  const { user } = useAuth();
  const role = user?.role;
  const visible = TABS.filter((tab) => !tab.roles || tab.roles.includes(role));
  if (visible.length < 2) return null;
  return (
    <nav className="ctabs" aria-label="Console sections">
      {visible.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) => `ctabs__tab ${isActive ? "is-active" : ""}`}
        >
          <Icon name={tab.icon} size={14} />
          {tab.label}
        </NavLink>
      ))}
    </nav>
  );
}
