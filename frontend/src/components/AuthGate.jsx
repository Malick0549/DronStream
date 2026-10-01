import React, { useEffect, useState } from "react";
import LoginPage from "../pages/LoginPage";

const API_URL = "";

function AuthGate({ children }) {
  const [checking, setChecking] = useState(true);
  const [authed, setAuthed] = useState(false);

  async function checkAuth() {
    try {
      const res = await fetch(`${API_URL}/api/auth/me`, {
        credentials: "include",
      });
      const data = await res.json();
      setAuthed(data.authenticated === true);
    } catch (err) {
      console.warn("DroneStream: auth check failed:", err);
      setAuthed(false);
    } finally {
      setChecking(false);
    }
  }

  useEffect(() => {
    checkAuth();
  }, []);

  if (checking) {
    return (
      <div className="auth-loading">
        CHECKING AUTHENTICATION…
      </div>
    );
  }

  if (!authed) {
    return <LoginPage onLoginSuccess={() => setAuthed(true)} />;
  }

  return children;
}

export default AuthGate;