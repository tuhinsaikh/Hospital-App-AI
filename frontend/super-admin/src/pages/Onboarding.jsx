import { useState } from 'react';
import './Onboarding.css';

const STEPS = [
    { id: 1, label: 'Hospital Info', icon: '🏥' },
    { id: 2, label: 'HMS Connection', icon: '🔌' },
    { id: 3, label: 'Field Mapping', icon: '🗂️' },
    { id: 4, label: 'Confirm & Go', icon: '✅' },
];

export default function Onboarding() {
    const [step, setStep] = useState(1);
    const [formData, setFormData] = useState({
        hospitalName: '', city: '', state: '', beds: '',
        sourceType: 'database',
        dbUrl: '', apiUrl: '', apiKey: '',
        mappings: {},
    });
    const [testStatus, setTestStatus] = useState(null); // null | 'success' | 'error'
    const [suggestedMappings, setSuggestedMappings] = useState({});
    const [done, setDone] = useState(false);

    const update = (key, val) => setFormData(f => ({ ...f, [key]: val }));

    const testConnection = async () => {
        setTestStatus('testing');
        await new Promise(r => setTimeout(r, 1200));
        setTestStatus('success');
        // Mock AI-suggested mappings
        setSuggestedMappings({
            'pat_id': 'patient_id',
            'fname': 'first_name',
            'lname': 'last_name',
            'birth_dt': 'dob',
            'sex_cd': 'gender',
            'mob_no': 'phone',
            'email_id': 'email',
            'addr_line': 'address',
        });
    };

    if (done) {
        return (
            <div className="page-container">
                <div className="page-content onboarding-success animate-in">
                    <div className="success-icon">🎉</div>
                    <h2>Hospital Onboarded Successfully!</h2>
                    <p>{formData.hospitalName} is now connected to the platform.</p>
                    <button className="btn btn-primary" onClick={() => window.location.href = '/hospitals'}>
                        View All Hospitals →
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="page-container">
            <div className="page-content">
                <div className="page-header animate-in">
                    <h1>Onboard New Hospital</h1>
                    <p>Connect an existing HMS system to the platform in minutes</p>
                </div>

                {/* Step Progress Bar */}
                <div className="step-bar animate-in stagger-1">
                    {STEPS.map((s, i) => (
                        <div key={s.id} className={`step-item ${step === s.id ? 'active' : ''} ${step > s.id ? 'done' : ''}`}>
                            <div className="step-circle">{step > s.id ? '✓' : s.icon}</div>
                            <div className="step-label">{s.label}</div>
                            {i < STEPS.length - 1 && <div className="step-connector" />}
                        </div>
                    ))}
                </div>

                {/* Step Content */}
                <div className="card wizard-card animate-in stagger-2">
                    {step === 1 && (
                        <StepHospitalInfo formData={formData} update={update} />
                    )}
                    {step === 2 && (
                        <StepConnection formData={formData} update={update} testStatus={testStatus} onTest={testConnection} />
                    )}
                    {step === 3 && (
                        <StepMapping suggestedMappings={suggestedMappings} formData={formData} update={update} />
                    )}
                    {step === 4 && (
                        <StepConfirm formData={formData} suggestedMappings={suggestedMappings} />
                    )}

                    <div className="wizard-actions">
                        {step > 1 && (
                            <button className="btn btn-secondary" onClick={() => setStep(s => s - 1)}>
                                ← Back
                            </button>
                        )}
                        {step < 4 ? (
                            <button
                                id={`wizard-next-step-${step}`}
                                className="btn btn-primary"
                                onClick={() => setStep(s => s + 1)}
                                disabled={step === 2 && testStatus !== 'success'}
                            >
                                Next →
                            </button>
                        ) : (
                            <button
                                id="wizard-finish-btn"
                                className="btn btn-success"
                                onClick={() => setDone(true)}
                            >
                                🚀 Launch Integration
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

function StepHospitalInfo({ formData, update }) {
    return (
        <div className="step-content">
            <h3 className="step-title">Hospital Information</h3>
            <p className="step-desc">Enter the basic details of the hospital you are onboarding.</p>
            <div className="grid-2" style={{ marginTop: '1.5rem' }}>
                <div className="input-group" style={{ gridColumn: '1 / -1' }}>
                    <label>Hospital Name</label>
                    <input id="hospital-name" placeholder="City General Hospital" value={formData.hospitalName} onChange={e => update('hospitalName', e.target.value)} />
                </div>
                <div className="input-group">
                    <label>City</label>
                    <input id="hospital-city" placeholder="Mumbai" value={formData.city} onChange={e => update('city', e.target.value)} />
                </div>
                <div className="input-group">
                    <label>State</label>
                    <input id="hospital-state" placeholder="Maharashtra" value={formData.state} onChange={e => update('state', e.target.value)} />
                </div>
                <div className="input-group">
                    <label>Number of Beds</label>
                    <input id="hospital-beds" type="number" placeholder="450" value={formData.beds} onChange={e => update('beds', e.target.value)} />
                </div>
            </div>
        </div>
    );
}

function StepConnection({ formData, update, testStatus, onTest }) {
    return (
        <div className="step-content">
            <h3 className="step-title">HMS Connection</h3>
            <p className="step-desc">Select how to connect to the existing HMS system. We only read data — no changes are ever made.</p>

            <div className="source-type-group">
                {['database', 'api', 'file'].map(type => (
                    <button
                        key={type}
                        id={`source-${type}`}
                        className={`source-type-btn ${formData.sourceType === type ? 'selected' : ''}`}
                        onClick={() => update('sourceType', type)}
                    >
                        <span>{type === 'database' ? '🗄️' : type === 'api' ? '🌐' : '📄'}</span>
                        <span>{type === 'database' ? 'Database' : type === 'api' ? 'REST API' : 'File Upload'}</span>
                    </button>
                ))}
            </div>

            {formData.sourceType === 'database' && (
                <div className="input-group" style={{ marginTop: '1.5rem' }}>
                    <label>Database URL</label>
                    <input id="db-url" placeholder="postgresql://user:pass@host:5432/dbname" value={formData.dbUrl} onChange={e => update('dbUrl', e.target.value)} />
                </div>
            )}

            {formData.sourceType === 'api' && (
                <div className="grid-2" style={{ marginTop: '1.5rem' }}>
                    <div className="input-group" style={{ gridColumn: '1 / -1' }}>
                        <label>API Base URL</label>
                        <input id="api-url" placeholder="https://api.hospital.com/v1" value={formData.apiUrl} onChange={e => update('apiUrl', e.target.value)} />
                    </div>
                    <div className="input-group" style={{ gridColumn: '1 / -1' }}>
                        <label>API Key / Bearer Token</label>
                        <input id="api-key" type="password" placeholder="••••••••••••" value={formData.apiKey} onChange={e => update('apiKey', e.target.value)} />
                    </div>
                </div>
            )}

            <button
                id="test-connection-btn"
                className={`btn test-btn ${testStatus === 'success' ? 'btn-success' : testStatus === 'error' ? 'btn-danger' : 'btn-secondary'}`}
                onClick={onTest}
                disabled={testStatus === 'testing'}
                style={{ marginTop: '1.5rem' }}
            >
                {testStatus === 'testing' && <span className="spinner" />}
                {testStatus === 'success' ? '✅ Connection Successful' :
                    testStatus === 'error' ? '❌ Connection Failed' :
                        '🔌 Test Connection'}
            </button>
            {testStatus === 'success' && (
                <p className="success-note">Successfully connected! AI is scanning the schema for field mapping suggestions.</p>
            )}
        </div>
    );
}

function StepMapping({ suggestedMappings, formData, update }) {
    return (
        <div className="step-content">
            <h3 className="step-title">Field Mapping</h3>
            <p className="step-desc">
                AI has suggested mappings based on the HMS schema. Review and adjust if needed.
            </p>
            <div className="mapping-table" style={{ marginTop: '1.5rem' }}>
                <div className="mapping-header">
                    <span>HMS Field</span>
                    <span>→</span>
                    <span>Standard Field</span>
                </div>
                {Object.entries(suggestedMappings).map(([hms, std]) => (
                    <div key={hms} className="mapping-row">
                        <code className="field-code">{hms}</code>
                        <span className="mapping-arrow">→</span>
                        <select
                            className="mapping-select"
                            defaultValue={std || ''}
                            onChange={e => update('mappings', { ...formData.mappings, [hms]: e.target.value })}
                        >
                            <option value="">-- Skip --</option>
                            {['patient_id', 'first_name', 'last_name', 'dob', 'gender', 'phone', 'email', 'address'].map(f => (
                                <option key={f} value={f}>{f}</option>
                            ))}
                        </select>
                    </div>
                ))}
            </div>
        </div>
    );
}

function StepConfirm({ formData, suggestedMappings }) {
    return (
        <div className="step-content">
            <h3 className="step-title">Review & Confirm</h3>
            <p className="step-desc">Everything looks good! Review the details before launching the integration.</p>
            <div className="confirm-grid">
                <div className="confirm-block">
                    <h4>🏥 Hospital</h4>
                    <p>{formData.hospitalName || 'N/A'}</p>
                    <p>{formData.city}, {formData.state}</p>
                    <p>{formData.beds} beds</p>
                </div>
                <div className="confirm-block">
                    <h4>🔌 Connection</h4>
                    <p>Type: <strong>{formData.sourceType}</strong></p>
                    <p>{formData.dbUrl || formData.apiUrl || 'File-based'}</p>
                </div>
                <div className="confirm-block">
                    <h4>🗂️ Mappings</h4>
                    <p>{Object.keys(suggestedMappings).length} fields mapped</p>
                </div>
            </div>
        </div>
    );
}
