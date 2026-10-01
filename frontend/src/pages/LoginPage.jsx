import React, { useState } from "react";

const API_URL = "";

function LoginPage({ onLoginSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();

    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username, password }),
      });

      const data = await res.json();

      if (res.ok && data.success) {
        onLoginSuccess();
      } else {
        setError(data.message || "Login failed.");
      }
    } catch (err) {
      console.error("DroneStream: login error:", err);
      setError("Unable to reach the DroneStream server.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="viewer-page">
      <header className="viewer-header">
        <div className="brand">DRONESTREAM</div>
        <div className="viewer-status offline">ADMIN LOGIN</div>
      </header>

      <main
        className="viewer-content"
        style={{
          display: "grid",
          placeItems: "center",
          minHeight: "60vh",
        }}
      >
        <form className="login-form" onSubmit={handleSubmit}>
          <label>
            USERNAME
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </label>

          <label>
            PASSWORD
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          {error && <div className="login-error">{error}</div>}

          <button type="submit" disabled={loading}>
            {loading ? "Signing in…" : "Log In"}
          </button>
        </form>
      </main>
    </div>
  );
}

export default LoginPage;