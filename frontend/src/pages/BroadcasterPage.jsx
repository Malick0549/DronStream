import { useEffect, useRef, useState } from "react";
import "./BroadcasterPage.css";

const API_URL = "";
function waitForIceGathering(peer) {
  if (peer.iceGatheringState === "complete") return Promise.resolve();

  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      peer.removeEventListener("icegatheringstatechange", onChange);
      reject(new Error("ICE gathering timed out. Check the network and TURN configuration."));
    }, 15000);
    const onChange = () => {
      if (peer.iceGatheringState === "complete") {
        window.clearTimeout(timeout);
        peer.removeEventListener("icegatheringstatechange", onChange);
        resolve();
      }
    };
    peer.addEventListener("icegatheringstatechange", onChange);
  });
}

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
  if (!response.ok) throw new Error(data.detail || data.message || "Request failed.");
  return data;
}

export default function BroadcasterPage() {
  const previewRef = useRef(null);
  const peerRef = useRef(null);
  const captureRef = useRef(null);
  const [account, setAccount] = useState(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState(new URLSearchParams(window.location.search).has("invite") ? "register" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [invite, setInvite] = useState(new URLSearchParams(window.location.search).get("invite") || "");
  const [streams, setStreams] = useState([]);
  const [selectedStream, setSelectedStream] = useState("");
  const [viewerUrl, setViewerUrl] = useState("");
  const [links, setLinks] = useState([]);
  const [viewers, setViewers] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const [isLive, setIsLive] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function loadStreams(preferredStream = "") {
    const data = await requestJson("/api/accounts/streams");
    setStreams(data.streams || []);
    setSelectedStream((current) => preferredStream || current || data.streams?.find((stream) => stream.status !== "live")?.id || "");
  }

  async function loadStreamTools(streamKey = selectedStream) {
    if (!streamKey || !account) return;
    const requests = [];
    if (account.permissions.can_manage_links) {
      requests.push(requestJson(`/api/accounts/streams/${encodeURIComponent(streamKey)}/links`)
        .then((data) => setLinks(data.links || [])));
    } else {
      setLinks([]);
    }
    if (account.permissions.can_manage_viewers) {
      requests.push(requestJson(`/api/accounts/streams/${encodeURIComponent(streamKey)}/viewers`)
        .then((data) => setViewers(data.viewers || [])));
    } else {
      setViewers([]);
    }
    await Promise.all(requests);
  }

  useEffect(() => {
    if (account && selectedStream) {
      loadStreamTools().catch((err) => setError(err.message));
    }
  }, [account, selectedStream]);

  useEffect(() => {
    let active = true;
    requestJson("/api/accounts/me")
      .then((data) => {
        if (!active || !data.authenticated) return;
        setAccount(data.account);
        return Promise.all([loadStreams(), refreshDevices()]);
      })
      .catch(() => {})
      .finally(() => active && setChecking(false));
    return () => {
      active = false;
      peerRef.current?.close();
      captureRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function refreshDevices() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cameras = devices.filter((device) => device.kind === "videoinput");
    setDevices(cameras);
    if (!deviceId && cameras[0]) setDeviceId(cameras[0].deviceId);
  }

  async function authenticate(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      const path = mode === "register" ? "/api/accounts/register" : "/api/accounts/login";
      const body = mode === "register"
        ? { invite_token: invite, username, password }
        : { username, password };
      const data = await requestJson(path, { method: "POST", body: JSON.stringify(body) });
      setAccount(data.account);
      await loadStreams();
    } catch (err) {
      setError(err.message);
    }
  }

  async function createStream() {
    setError("");
    try {
      const data = await requestJson("/api/accounts/streams", {
        method: "POST",
        body: JSON.stringify({ title: "Live stream" }),
      });
      const url = `${window.location.origin}/watch/${encodeURIComponent(data.viewer_token)}`;
      setViewerUrl(data.viewer_token ? url : "");
      await loadStreams(data.stream.id);
      setMessage("Stream created. Connect a video source to go live.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function createViewerLink() {
    try {
      const data = await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/links`, {
        method: "POST",
        body: JSON.stringify({ expires_in_hours: 72 }),
      });
      const url = `${window.location.origin}/watch/${encodeURIComponent(data.link.token)}`;
      setViewerUrl(url);
      await loadStreamTools();
      setMessage("Viewer link created.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function revokeViewerLink(linkId) {
    try {
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/links/${linkId}`, { method: "DELETE" });
      await loadStreamTools();
      setMessage("Viewer link revoked.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function updateViewerPermission(viewer, permission, allowed) {
    try {
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/viewers/${encodeURIComponent(viewer.session_id)}/permissions`, {
        method: "PATCH",
        body: JSON.stringify({ [permission]: allowed }),
      });
      setMessage("Viewer permissions updated.");
    } catch (err) {
      setError(err.message);
      await loadStreamTools();
    }
  }

  async function kickViewer(viewer) {
    try {
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/viewers/${encodeURIComponent(viewer.session_id)}/kick`, { method: "POST" });
      await loadStreamTools();
      setMessage("Viewer removed from the stream.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleRecording() {
    const action = isRecording ? "stop" : "start";
    try {
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/recording/${action}`, { method: "POST" });
      setIsRecording(!isRecording);
      setMessage(isRecording ? "Recording saved." : "Recording started.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function captureScreenshot() {
    try {
      const data = await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/screenshot`, { method: "POST" });
      setMessage(`Screenshot saved: ${data.screenshot.file_name}`);
    } catch (err) {
      setError(err.message);
    }
  }

  async function startBroadcast() {
    if (!selectedStream) return;
    setIsStarting(true);
    setError("");
    setMessage("");
    let capture;
    let peer;
    try {
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/start`, { method: "POST" });
      capture = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
          width: { ideal: 1280 },
          height: { ideal: 720 },
          frameRate: { ideal: 30, max: 30 },
        },
      });
      captureRef.current = capture;
      if (previewRef.current) {
        previewRef.current.srcObject = capture;
        await previewRef.current.play();
      }
      await refreshDevices();

      const iceConfig = await requestJson("/api/webrtc/ice-config");
      peer = new RTCPeerConnection({ iceServers: iceConfig.iceServers || [] });
      peerRef.current = peer;
      capture.getTracks().forEach((track) => peer.addTrack(track, capture));
      peer.onconnectionstatechange = () => {
        if (peer.connectionState === "connected") {
          setIsLive(true);
          setIsStarting(false);
          setMessage("Broadcast connected. Your viewers can watch now.");
          loadStreams().catch(() => {});
        } else if (["failed", "closed"].includes(peer.connectionState)) {
          setIsLive(false);
        }
      };

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      await waitForIceGathering(peer);
      const answer = await requestJson("/api/webrtc/broadcast/offer", {
        method: "POST",
        body: JSON.stringify({
          stream_id: selectedStream,
          sdp: peer.localDescription.sdp,
          type: peer.localDescription.type,
        }),
      });
      await peer.setRemoteDescription({ type: answer.type, sdp: answer.sdp });
    } catch (err) {
      peer?.close();
      if (peerRef.current === peer) peerRef.current = null;
      capture?.getTracks().forEach((track) => track.stop());
      if (captureRef.current === capture) captureRef.current = null;
      if (previewRef.current) previewRef.current.srcObject = null;
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/stop`, { method: "POST" }).catch(() => {});
      setError(err.message);
      setIsStarting(false);
    }
  }

  async function stopBroadcast() {
    const peer = peerRef.current;
    peerRef.current = null;
    peer?.close();
    const capture = captureRef.current;
    captureRef.current = null;
    capture?.getTracks().forEach((track) => track.stop());
    if (previewRef.current) previewRef.current.srcObject = null;
    try {
      await requestJson(`/api/accounts/streams/${encodeURIComponent(selectedStream)}/stop`, { method: "POST" });
      setMessage("Broadcast stopped.");
      await loadStreams();
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLive(false);
      setIsStarting(false);
    }
  }

  async function logout() {
    if (selectedStream && (isLive || isStarting)) {
      await stopBroadcast();
    }
    await requestJson("/api/accounts/logout", { method: "POST" }).catch(() => {});
    setAccount(null);
    setStreams([]);
    setViewerUrl("");
  }

  if (checking) return <main className="broadcaster-shell"><p>Checking account…</p></main>;

  if (!account) {
    return (
      <main className="broadcaster-shell">
        <section className="broadcaster-auth">
          <a href="/" className="broadcaster-back">DroneStream</a>
          <p className="broadcaster-kicker">BROADCASTER ACCESS</p>
          <h1>{mode === "register" ? "Create your account" : "Sign in to broadcast"}</h1>
          <form onSubmit={authenticate} className="broadcaster-form">
            {mode === "register" && <label>Invite token<input value={invite} onChange={(event) => setInvite(event.target.value)} required /></label>}
            <label>Username<input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} /></label>
            <label>Password<input type="password" autoComplete={mode === "register" ? "new-password" : "current-password"} value={password} onChange={(event) => setPassword(event.target.value)} required minLength={mode === "register" ? 12 : 1} /></label>
            {error && <p className="broadcaster-error" role="alert">{error}</p>}
            <button className="broadcaster-primary" type="submit">{mode === "register" ? "Create account" : "Sign in"}</button>
          </form>
          <button className="broadcaster-text-button" onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(""); }}>
            {mode === "register" ? "Already have an account? Sign in" : "Have an invite? Create an account"}
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="broadcaster-shell">
      <header className="broadcaster-topbar">
        <a href="/" className="broadcaster-back">DroneStream <span>/ BROADCAST</span></a>
        <div><span className="broadcaster-identity">{account.username}</span><button className="broadcaster-text-button" onClick={logout}>Sign out</button></div>
      </header>
      <section className="broadcaster-layout">
        <div className="broadcaster-heading">
          <div><p className="broadcaster-kicker">TRANSMISSION CONTROL</p><h1>Your broadcast</h1></div>
          <span className={`broadcaster-status ${isLive ? "is-live" : ""}`}><i />{isLive ? "LIVE" : isStarting ? "CONNECTING" : "OFFLINE"}</span>
        </div>
        <div className="broadcaster-grid">
          <section className="broadcaster-preview-panel">
            <video ref={previewRef} autoPlay muted playsInline />
            {!isLive && !isStarting && <div className="broadcaster-empty">Select a source and start your broadcast</div>}
            {isStarting && <div className="broadcaster-empty">Establishing secure media connection…</div>}
          </section>
          <section className="broadcaster-controls">
            <label>Stream<select value={selectedStream} onChange={(event) => { setSelectedStream(event.target.value); setViewerUrl(""); }} disabled={isLive || isStarting}>
              <option value="">Choose a stream</option>
              {streams.map((stream) => <option key={stream.id} value={stream.id}>{stream.id.slice(0, 14)} · {stream.status}</option>)}
            </select></label>
            <label>Video source<select value={deviceId} onChange={(event) => setDeviceId(event.target.value)} disabled={isLive || isStarting}>
              <option value="">Default camera or capture card</option>
              {devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Video input ${index + 1}`}</option>)}
            </select></label>
            <div className="broadcaster-actions">
              <button className="broadcaster-secondary" onClick={createStream} disabled={isLive || isStarting || !account.permissions.can_start_streams}>New stream</button>
              {!isLive ? <button className="broadcaster-primary" onClick={startBroadcast} disabled={!selectedStream || isStarting || !account.permissions.can_start_streams}>{isStarting ? "Connecting…" : "Go live"}</button> : <button className="broadcaster-stop" onClick={stopBroadcast}>Stop broadcast</button>}
            </div>
            {isLive && (account.permissions.can_record || account.permissions.can_screenshot) && <div className="broadcaster-actions">
              {account.permissions.can_record && <button className={isRecording ? "broadcaster-stop" : "broadcaster-secondary"} onClick={toggleRecording}>{isRecording ? "Stop recording" : "Record"}</button>}
              {account.permissions.can_screenshot && <button className="broadcaster-secondary" onClick={captureScreenshot}>Capture screenshot</button>}
            </div>}
            {viewerUrl && <div className="broadcaster-share">
              <span>VIEWER LINK</span>
              <a href={viewerUrl} target="_blank" rel="noreferrer">{viewerUrl}</a>
              <div className="broadcaster-social-links">
                <button className="broadcaster-secondary" onClick={() => navigator.clipboard.writeText(viewerUrl).then(() => setMessage("Viewer link copied."))}>Copy</button>
                <a href={`https://wa.me/?text=${encodeURIComponent(viewerUrl)}`} target="_blank" rel="noreferrer">WhatsApp</a>
                <a href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(viewerUrl)}`} target="_blank" rel="noreferrer">Facebook</a>
                <a href={`https://t.me/share/url?url=${encodeURIComponent(viewerUrl)}`} target="_blank" rel="noreferrer">Telegram</a>
                <a href={`https://twitter.com/intent/tweet?url=${encodeURIComponent(viewerUrl)}`} target="_blank" rel="noreferrer">X</a>
                {navigator.share && <button className="broadcaster-secondary" onClick={() => navigator.share({ title: "DroneStream live feed", url: viewerUrl }).catch(() => {})}>More</button>}
              </div>
            </div>}
            {selectedStream && account.permissions.can_manage_links && <section className="broadcaster-tools">
              <div className="broadcaster-tools-heading"><strong>Viewer links</strong><button className="broadcaster-text-button" onClick={createViewerLink}>New link</button></div>
              {links.map((link) => <div className="broadcaster-tool-row" key={link.id}><span>{link.revoked ? "Revoked" : link.expires_at ? `Expires ${new Date(link.expires_at).toLocaleString()}` : "Active"}</span><button className="broadcaster-text-button" onClick={() => navigator.clipboard.writeText(`${window.location.origin}/watch/${encodeURIComponent(link.token)}`).then(() => setMessage("Viewer link copied."))}>Copy</button>{!link.revoked && <button className="broadcaster-text-button danger" onClick={() => revokeViewerLink(link.id)}>Revoke</button>}</div>)}
            </section>}
            {selectedStream && account.permissions.can_manage_viewers && <section className="broadcaster-tools">
              <div className="broadcaster-tools-heading"><strong>Viewer sessions</strong><button className="broadcaster-text-button" onClick={() => loadStreamTools()}>Refresh</button></div>
              {viewers.filter((viewer) => viewer.status === "watching").map((viewer) => <div className="broadcaster-viewer-row" key={viewer.session_id}>
                <span>{viewer.ip_address || "Viewer"}<small>{new Date(viewer.connected_at).toLocaleTimeString()}</small></span>
                {account.permissions.can_record && <label title="Allow recording"><input type="checkbox" checked={viewer.can_record} onChange={(event) => updateViewerPermission(viewer, "can_record", event.target.checked)} />Record</label>}
                {account.permissions.can_screenshot && <label title="Allow screenshots"><input type="checkbox" checked={viewer.can_screenshot} onChange={(event) => updateViewerPermission(viewer, "can_screenshot", event.target.checked)} />Screenshot</label>}
                <button className="broadcaster-text-button danger" onClick={() => kickViewer(viewer)}>Remove</button>
              </div>)}
              {viewers.filter((viewer) => viewer.status === "watching").length === 0 && <p className="broadcaster-muted">No active viewers.</p>}
            </section>}
            {message && <p className="broadcaster-message" role="status">{message}</p>}
            {error && <p className="broadcaster-error" role="alert">{error}</p>}
          </section>
        </div>
      </section>
    </main>
  );
}