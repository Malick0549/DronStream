import { useEffect, useState } from "react";
import "./BroadcastersAdminPage.css";

const API_URL = "";
const PERMISSIONS = [
  ["can_start_streams", "Broadcast"],
  ["can_manage_links", "Manage links"],
  ["can_manage_viewers", "Manage viewers"],
  ["can_record", "Record"],
  ["can_screenshot", "Screenshots"],
];

async function requestJson(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Request failed.");
  return data;
}

export default function BroadcastersAdminPage({ navigate }) {
  const [accounts, setAccounts] = useState([]);
  const [inviteHours, setInviteHours] = useState(72);
  const [inviteUrl, setInviteUrl] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function loadAccounts() {
    const data = await requestJson("/api/admin/broadcasters");
    setAccounts(data.accounts || []);
  }

  useEffect(() => {
    loadAccounts().catch((err) => setError(err.message));
  }, []);

  async function createInvite(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const data = await requestJson("/api/admin/broadcasters/invites", {
        method: "POST",
        body: JSON.stringify({ expires_in_hours: Number(inviteHours) }),
      });
      setInviteUrl(`${window.location.origin}/broadcast?invite=${encodeURIComponent(data.invite_token)}`);
      setMessage("Invite created. Share it with the broadcaster; it can be used once.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function updateAccount(account, change) {
    setBusyId(account.id);
    setError("");
    setMessage("");
    try {
      const data = await requestJson(`/api/admin/broadcasters/${account.id}`, {
        method: "PATCH",
        body: JSON.stringify(change),
      });
      setAccounts((current) => current.map((item) => item.id === account.id ? data.account : item));
      setMessage(`Updated permissions for ${account.username}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="broadcasters-admin">
      <header className="broadcasters-admin-header">
        <button onClick={() => navigate("/")} aria-label="Back to dashboard">← Dashboard</button>
        <span>ADMINISTRATION / BROADCASTERS</span>
      </header>
      <section className="broadcasters-admin-content">
        <div className="broadcasters-admin-title">
          <div><p>ACCOUNT ACCESS</p><h1>Broadcasters</h1></div>
          <span>{accounts.length} account{accounts.length === 1 ? "" : "s"}</span>
        </div>

        <form className="broadcaster-invite-form" onSubmit={createInvite}>
          <div><label htmlFor="invite-expiry">Invite expiration</label><select id="invite-expiry" value={inviteHours} onChange={(event) => setInviteHours(event.target.value)}><option value="24">24 hours</option><option value="72">3 days</option><option value="168">7 days</option></select></div>
          <button type="submit">Create invite link</button>
        </form>
        {inviteUrl && <div className="broadcaster-invite-result"><a href={inviteUrl}>{inviteUrl}</a><button onClick={() => navigator.clipboard.writeText(inviteUrl).then(() => setMessage("Invite link copied."))}>Copy</button></div>}
        {message && <p className="broadcaster-admin-message" role="status">{message}</p>}
        {error && <p className="broadcaster-admin-error" role="alert">{error}</p>}

        <div className="broadcasters-table-wrap">
          <table className="broadcasters-table">
            <thead><tr><th>Broadcaster</th><th>Account</th>{PERMISSIONS.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead>
            <tbody>
              {accounts.map((account) => <tr key={account.id}>
                <td>{account.username}</td>
                <td><button className={`account-state ${account.is_active ? "active" : "disabled"}`} disabled={busyId === account.id} onClick={() => updateAccount(account, { is_active: !account.is_active })}>{account.is_active ? "Active" : "Disabled"}</button></td>
                {PERMISSIONS.map(([key, label]) => <td key={key}><label className="permission-toggle" title={`${label} permission`}><input type="checkbox" checked={Boolean(account.permissions?.[key])} disabled={!account.is_active || busyId === account.id} onChange={(event) => updateAccount(account, { [key]: event.target.checked })} /><span /></label></td>)}
              </tr>)}
              {accounts.length === 0 && <tr><td colSpan={2 + PERMISSIONS.length} className="empty-broadcasters">No broadcaster accounts yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}