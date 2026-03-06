import { NavLink } from 'react-router-dom';
import './Sidebar.css';

const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: '📊' },
    { path: '/hospitals', label: 'Hospitals', icon: '🏥' },
    { path: '/onboarding', label: 'Onboarding', icon: '🚀' },
];

export default function Sidebar() {
    return (
        <aside className="sidebar">
            <div className="sidebar-brand">
                <div className="brand-icon">⚕️</div>
                <div>
                    <span className="brand-name">HMS Platform</span>
                    <span className="brand-sub">Super Admin</span>
                </div>
            </div>

            <nav className="sidebar-nav">
                {navItems.map(item => (
                    <NavLink
                        key={item.path}
                        to={item.path}
                        className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                    >
                        <span className="nav-icon">{item.icon}</span>
                        <span className="nav-label">{item.label}</span>
                    </NavLink>
                ))}
            </nav>

            <div className="sidebar-footer">
                <div className="user-pill">
                    <div className="user-avatar">SA</div>
                    <div>
                        <div className="user-name">Super Admin</div>
                        <div className="user-role">Platform Operator</div>
                    </div>
                </div>
            </div>
        </aside>
    );
}
