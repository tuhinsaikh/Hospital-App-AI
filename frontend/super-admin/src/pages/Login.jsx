import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './Login.css';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        // Simulate auth (swap with real API later)
        await new Promise(r => setTimeout(r, 1000));
        setLoading(false);
        navigate('/dashboard');
    };

    return (
        <div className="login-page">
            <div className="login-bg-orbs">
                <div className="orb orb-1" />
                <div className="orb orb-2" />
                <div className="orb orb-3" />
            </div>

            <div className="login-card animate-in">
                <div className="login-brand">
                    <div className="login-brand-icon">⚕️</div>
                    <h1>HMS Platform</h1>
                    <p>Super Admin Portal</p>
                </div>

                <form className="login-form" onSubmit={handleSubmit}>
                    <div className="input-group">
                        <label htmlFor="email">Email Address</label>
                        <input
                            id="email"
                            type="email"
                            placeholder="admin@hmsplatform.com"
                            value={email}
                            onChange={e => setEmail(e.target.value)}
                            required
                        />
                    </div>

                    <div className="input-group">
                        <label htmlFor="password">Password</label>
                        <input
                            id="password"
                            type="password"
                            placeholder="••••••••"
                            value={password}
                            onChange={e => setPassword(e.target.value)}
                            required
                        />
                    </div>

                    <button
                        id="login-btn"
                        type="submit"
                        className="btn btn-primary login-submit"
                        disabled={loading}
                    >
                        {loading ? <span className="spinner" /> : null}
                        {loading ? 'Authenticating…' : 'Sign In →'}
                    </button>
                </form>

                <p className="login-footer">
                    Hospital Management System Platform &copy; 2026
                </p>
            </div>
        </div>
    );
}
