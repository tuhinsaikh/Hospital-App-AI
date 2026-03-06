import './Dashboard.css';

const stats = [
    { label: 'Total Hospitals', value: '12', delta: '+2 this month', icon: '🏥', color: 'indigo' },
    { label: 'Active Adapters', value: '9', delta: '3 DB, 4 API, 2 File', icon: '🔌', color: 'cyan' },
    { label: 'Data Sync Jobs', value: '47', delta: '+5 today', icon: '🔄', color: 'green' },
    { label: 'Pending Setups', value: '3', delta: 'Action required', icon: '⚠️', color: 'amber' },
];

const hospitals = [
    { name: 'City General Hospital', source: 'PostgreSQL', status: 'active', sync: '2 min ago' },
    { name: 'St. Mary\'s Medical', source: 'REST API', status: 'active', sync: '8 min ago' },
    { name: 'Northern Clinic Group', source: 'MySQL', status: 'active', sync: '15 min ago' },
    { name: 'Sunrise Health Network', source: 'CSV Import', status: 'pending', sync: 'Not synced' },
    { name: 'Metro Children\'s Center', source: 'REST API', status: 'active', sync: '1 hr ago' },
];

export default function Dashboard() {
    return (
        <div className="page-container">
            <div className="page-content">
                <div className="page-header animate-in">
                    <h1>Platform Overview</h1>
                    <p>Real-time status of all connected hospitals and adapters</p>
                </div>

                {/* Stats Grid */}
                <div className="grid-4 animate-in stagger-1">
                    {stats.map((s, i) => (
                        <div key={i} className={`stat-card card stat-card--${s.color}`}>
                            <div className="stat-icon">{s.icon}</div>
                            <div className="stat-value">{s.value}</div>
                            <div className="stat-label">{s.label}</div>
                            <div className="stat-delta">{s.delta}</div>
                        </div>
                    ))}
                </div>

                {/* Hospitals Table */}
                <div className="card animate-in stagger-2" style={{ marginTop: '1.5rem' }}>
                    <div className="table-header">
                        <h2>Connected Hospitals</h2>
                        <a href="/hospitals" className="btn btn-primary">+ Add Hospital</a>
                    </div>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Hospital</th>
                                <th>Data Source</th>
                                <th>Status</th>
                                <th>Last Sync</th>
                            </tr>
                        </thead>
                        <tbody>
                            {hospitals.map((h, i) => (
                                <tr key={i}>
                                    <td className="hospital-name">{h.name}</td>
                                    <td><span className="source-tag">{h.source}</span></td>
                                    <td>
                                        <span className={`badge badge-${h.status === 'active' ? 'success' : 'warning'}`}>
                                            {h.status === 'active' ? '● Active' : '○ Pending'}
                                        </span>
                                    </td>
                                    <td className="sync-time">{h.sync}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}
