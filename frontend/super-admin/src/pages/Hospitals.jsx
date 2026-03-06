import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './Hospitals.css';

const mockHospitals = [
    { id: 1, name: 'City General Hospital', city: 'Mumbai', source: 'PostgreSQL', status: 'active', beds: 450 },
    { id: 2, name: "St. Mary's Medical", city: 'Delhi', source: 'REST API', status: 'active', beds: 320 },
    { id: 3, name: 'Northern Clinic Group', city: 'Bangalore', source: 'MySQL', status: 'active', beds: 180 },
    { id: 4, name: 'Sunrise Health Network', city: 'Chennai', source: 'CSV Import', status: 'pending', beds: 600 },
    { id: 5, name: "Metro Children's Center", city: 'Hyderabad', source: 'REST API', status: 'active', beds: 200 },
];

export default function Hospitals() {
    const [search, setSearch] = useState('');
    const navigate = useNavigate();

    const filtered = mockHospitals.filter(h =>
        h.name.toLowerCase().includes(search.toLowerCase()) ||
        h.city.toLowerCase().includes(search.toLowerCase())
    );

    return (
        <div className="page-container">
            <div className="page-content">
                <div className="page-header animate-in">
                    <h1>Hospital Management</h1>
                    <p>Manage all onboarded hospitals and their integration status</p>
                </div>

                <div className="hospitals-toolbar animate-in stagger-1">
                    <div className="input-group search-group">
                        <input
                            id="hospital-search"
                            type="text"
                            placeholder="🔍  Search hospitals..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                        />
                    </div>
                    <button
                        id="new-hospital-btn"
                        className="btn btn-primary"
                        onClick={() => navigate('/onboarding')}
                    >
                        + Onboard New Hospital
                    </button>
                </div>

                <div className="hospitals-grid animate-in stagger-2">
                    {filtered.map(h => (
                        <div key={h.id} className="hospital-card card">
                            <div className="hospital-card-header">
                                <div className="hospital-icon">🏥</div>
                                <span className={`badge badge-${h.status === 'active' ? 'success' : 'warning'}`}>
                                    {h.status === 'active' ? '● Active' : '○ Pending'}
                                </span>
                            </div>
                            <h3 className="hospital-card-name">{h.name}</h3>
                            <p className="hospital-card-city">📍 {h.city}</p>
                            <div className="hospital-card-meta">
                                <div className="meta-item">
                                    <span className="meta-label">Data Source</span>
                                    <span className="source-tag">{h.source}</span>
                                </div>
                                <div className="meta-item">
                                    <span className="meta-label">Beds</span>
                                    <span className="meta-value">{h.beds}</span>
                                </div>
                            </div>
                            <button className="btn btn-secondary hospital-manage-btn">
                                Manage →
                            </button>
                        </div>
                    ))}
                </div>

                {filtered.length === 0 && (
                    <div className="empty-state animate-in">
                        <div className="empty-icon">🏥</div>
                        <p>No hospitals found matching your search.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
