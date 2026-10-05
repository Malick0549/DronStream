import AuthGate from "./components/AuthGate";
import BroadcasterPage from "./pages/BroadcasterPage";
import BroadcastersAdminPage from "./pages/BroadcastersAdminPage";
import React from "react";
import { useEffect, useState } from "react";

const API_URL = "";

// ============================================================
// HELPER FUNCTIONS
// ============================================================

function formatDuration(seconds) {
  const totalSeconds = Math.max(0, Number(seconds) || 0);

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  }

  if (minutes > 0) {
    return `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`;
  }

  return `${remainingSeconds}s`;
}

function formatViewerStatus(status) {
  const s = String(status || "").toLowerCase();
  if (s === "watching") return "Watching";
  if (s === "kicked") return "Kicked";
  if (s === "timeout") return "Timed out";
  if (s === "revoked") return "Link revoked";
  if (s === "stream_ended") return "Stream ended";
  if (s === "disconnected") return "Disconnected";
  return "Ended";
}

function formatConnectionTime(dateString) {
if (!dateString) return "—";

try {
const date = new Date(dateString);

return date.toLocaleTimeString([], {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

} catch {
return "—";
}
}

function getBrowserName(userAgent) {
if (!userAgent || userAgent === "unknown") {
return "Unknown browser";
}

const ua = userAgent.toLowerCase();

if (ua.includes("edg/")) {
return "Microsoft Edge";
}

if (ua.includes("opr/") || ua.includes("opera")) {
return "Opera";
}

if (ua.includes("chrome") && !ua.includes("edg")) {
return "Google Chrome";
}

if (ua.includes("firefox")) {
return "Mozilla Firefox";
}

if (
ua.includes("safari") &&
!ua.includes("chrome")
) {
return "Safari";
}

return "Unknown browser";
}

function formatViewerLocation(session) {
  const city = session?.city;
  const region = session?.region;
  const country = session?.country;
  const parts = [city, region, country].filter(Boolean);
  if (parts.length === 0) return "—";
  return parts.join(", ");
}

function getDeviceType(userAgent) {
if (!userAgent || userAgent === "unknown") {
return "Unknown device";
}

const ua = userAgent.toLowerCase();

if (/ipad|tablet/.test(ua)) {
return "Tablet";
}

if (/mobile|android|iphone|ipod/.test(ua)) {
return "Mobile";
}

return "Desktop";
}

// ============================================================
// ADMIN NAVIGATION
// ============================================================

function AdminNavigation({ currentPage, navigate }) {
return ( <nav className="admin-navigation">

  <button
    className={`admin-nav-link ${
      currentPage === "dashboard" ? "active" : ""
    }`}
    onClick={() => navigate("/")}
  >
    <span>⌂</span>
    Dashboard
  </button>


  <button
    className={`admin-nav-link ${
      currentPage === "viewers" ? "active" : ""
    }`}
    onClick={() => navigate("/admin/viewers")}
  >
    <span>◉</span>
    Viewer Monitoring
  </button>


  <button
    className={`admin-nav-link ${
      currentPage === "recordings" ? "active" : ""
    }`}
    onClick={() => navigate("/admin/recordings")}
  >
    <span>▣</span>
    Recordings
  </button>


<button
  className={`admin-nav-link ${
    currentPage === "screenshots" ? "active" : ""
  }`}
  onClick={() => navigate("/admin/screenshots")}
>
  <span>▤</span>
  Screenshots
</button>


 <button
    className={`admin-nav-link ${
      currentPage === "settings" ? "active" : ""
    }`}
    onClick={() => navigate("/admin/settings")}
  >
    <span>⚙</span>
    Settings
  </button>

  <button
    className={`admin-nav-link ${
      currentPage === "broadcasters" ? "active" : ""
    }`}
    onClick={() => navigate("/admin/broadcasters")}
  >
    <span>◎</span>
    Broadcasters
  </button>

  <button
    className={`admin-nav-link ${
      currentPage === "security" ? "active" : ""
    }`}
    onClick={() => navigate("/admin/security")}
  >
    <span>⌕</span>
    Security Logs
  </button>

</nav>

);
}

// ============================================================
// ADMIN PAGE HEADER
// ============================================================

function AdminHeader({ isLive }) {
async function handleLogout() {
try {
await fetch(`${API_URL}/api/auth/logout`, {
method: "POST",
credentials: "include",
});
} catch (err) {
console.warn("DroneStream: logout error:", err);
}
window.location.reload();
}

return ( <header className="topbar">

  <div className="brand">

    <div className="brand-icon">
      <img
        src="/logo.jpeg"
        alt="DroneStream"
        className="brand-logo"
      />
    </div>

    <div>

      <div className="brand-name">
        DRONESTREAM
      </div>

      <div className="brand-subtitle">
        Secure Live Aerial Streaming
      </div>

    </div>

  </div>

  <div
    style={{
      display: "flex",
      alignItems: "center",
      gap: "16px",
    }}
  >

    <div
      className={`connection ${
        isLive ? "live" : ""
      }`}
    >

      <span className="connection-dot"></span>

      {isLive
        ? "LIVE"
        : "OFFLINE"}

    </div>

    <button
      onClick={handleLogout}
      style={{
        padding: "8px 14px",
        border: "1px solid #303846",
        borderRadius: "8px",
        background: "#0b0f16",
        color: "#c4cad5",
        fontSize: "11px",
        fontWeight: "700",
        letterSpacing: "0.08em",
        cursor: "pointer",
      }}
    >
      LOG OUT
    </button>

  </div>

</header>

);
}

// ============================================================
// ADMIN LIVE PREVIEW
// ============================================================

function AdminLivePreview({ isLive }) {
const videoRef = React.useRef(null);
const peerRef = React.useRef(null);

const [previewStatus, setPreviewStatus] =
useState("offline");

useEffect(() => {
let cancelled = false;

async function waitForIceGatheringComplete(pc) {
  if (pc.iceGatheringState === "complete") {
    return;
  }
  await new Promise((resolve) => {
    const check = () => {
      if (pc.iceGatheringState === "complete") {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      }
    };
    pc.addEventListener("icegatheringstatechange", check);
  });
}

async function startPreview() {
  if (!isLive) {
    setPreviewStatus("offline");

    if (peerRef.current) {
      peerRef.current.close();
      peerRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    return;
  }

  try {
    setPreviewStatus("connecting");

    const tokenResponse = await fetch(
      `${API_URL}/api/streams/preview-token`,
      {
        credentials: "include",
      }
    );

    if (!tokenResponse.ok) {
      throw new Error(
        "Unable to obtain preview token."
      );
    }

    const tokenData =
      await tokenResponse.json();

    if (
      cancelled ||
      !tokenData.success ||
      !tokenData.viewer_token
    ) {
      throw new Error(
        tokenData.message ||
        "Preview token unavailable."
      );
    }

    const isLocalHost =
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1";

    const peer = new RTCPeerConnection({
      iceServers: isLocalHost
        ? []
        : [
            { urls: "stun:stun.l.google.com:19302" },
            { urls: "stun:stun1.l.google.com:19302" },
          ],
    });

    peerRef.current = peer;

    peer.addTransceiver(
      "video",
      {
        direction: "recvonly",
      }
    );

    peer.ontrack = async (event) => {
      if (
        cancelled ||
        !videoRef.current
      ) {
        return;
      }

      const remoteStream =
        event.streams?.[0];

      if (!remoteStream) {
        return;
      }

      videoRef.current.srcObject =
        remoteStream;

      try {
        await videoRef.current.play();
      } catch (error) {
        console.warn(
          "DroneStream: admin preview play error:",
          error
        );
      }

      setPreviewStatus("live");
    };

    peer.onconnectionstatechange = () => {
      if (
        cancelled ||
        !peerRef.current
      ) {
        return;
      }

      const state =
        peer.connectionState;

      if (state === "connected") {
        setPreviewStatus("live");
      } else if (
        state === "failed" ||
        state === "disconnected" ||
        state === "closed"
      ) {
        setPreviewStatus("offline");
      }
    };

    const offer =
      await peer.createOffer();

    await peer.setLocalDescription(
      offer
    );

    await waitForIceGatheringComplete(peer);

    const response =
      await fetch(
        `${API_URL}/api/webrtc/offer`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type":
              "application/json",
          },
          body: JSON.stringify({
            sdp:
              peer.localDescription.sdp,
            type:
              peer.localDescription.type,
            viewer_token:
              tokenData.viewer_token,
          }),
        }
      );

    if (!response.ok) {
      throw new Error(
        "WebRTC preview connection failed."
      );
    }

    const answer =
      await response.json();

    if (
      !answer.sdp ||
      !answer.type
    ) {
      throw new Error(
        "Invalid WebRTC answer."
      );
    }

    await peer.setRemoteDescription(
      {
        type: answer.type,
        sdp: answer.sdp,
      }
    );

  } catch (error) {
    console.error(
      "DroneStream: admin preview error:",
      error
    );

    setPreviewStatus("error");

    if (peerRef.current) {
      peerRef.current.close();
      peerRef.current = null;
    }
  }
}

startPreview();

return () => {
  cancelled = true;

  if (peerRef.current) {
    peerRef.current.close();
    peerRef.current = null;
  }

  if (videoRef.current) {
    videoRef.current.srcObject = null;
  }
};

}, [isLive]);

return ( <div className="video-placeholder">

  {isLive ? (
    <>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          display:
            previewStatus === "live"
              ? "block"
              : "none",
        }}
      />

      {previewStatus !== "live" && (
        <div className="video-message">

          <div className="video-icon">
            ◉
          </div>

          <strong>
            {previewStatus === "error"
              ? "PREVIEW UNAVAILABLE"
              : "CONNECTING TO LIVE FEED"}
          </strong>

          <span>
            {previewStatus === "error"
              ? "Unable to connect to the stream"
              : "Connecting to DroneStream..."}
          </span>

        </div>
      )}
    </>
  ) : (
    <div className="video-message">

      <div className="video-icon">
        ◇
      </div>

      <strong>
        NO LIVE FEED
      </strong>

      <span>
        Start the stream to begin
        broadcasting
      </span>

    </div>
  )}

</div>

);
}

// ============================================================
// ADMIN DASHBOARD
// ============================================================

function AdminPage({ navigate }) {

const [stream, setStream] = useState(null);
const [loading, setLoading] = useState(false);
const [message, setMessage] = useState("");
const [viewerLink, setViewerLink] = useState("");
const [linkExpiryMinutes, setLinkExpiryMinutes] = useState("");
const [linkPassword, setLinkPassword] = useState("");
const [viewerSessions, setViewerSessions] = useState([]);
const [telemetry, setTelemetry] = useState(null);

const [dashboardRecording, setDashboardRecording] = useState(null);
const [recordingActionLoading, setRecordingActionLoading] = useState(false);
const [screenshotActionLoading, setScreenshotActionLoading] = useState(false);

// ----------------------------------------------------------
// Get stream status
// ----------------------------------------------------------

async function getStreamStatus() {

try {

  const response = await fetch(
    `${API_URL}/api/streams/status`,
    {
      credentials: "include",
    }
  );

  if (!response.ok) {
    return;
  }

  const data = await response.json();

    if (data.success) {
    setStream(data.stream);
    if (data.recording && data.recording.active) {
      setDashboardRecording(data.recording);
    } else {
      setDashboardRecording(null);
    }
  }

} catch (error) {

  console.warn(
    "DroneStream: stream status error:",
    error
  );

}

}

// ----------------------------------------------------------
// Get viewer count
// ----------------------------------------------------------

async function getViewerCount() {

try {

  const response = await fetch(
    `${API_URL}/api/viewer/sessions`,
    {
      credentials: "include",
    }
  );

  if (!response.ok) {
    return;
  }

  const data = await response.json();

  if (data.success) {

    setViewerSessions(
      data.sessions || []
    );

    setStream((currentStream) => {

      if (!currentStream) {
        return currentStream;
      }

      return {
        ...currentStream,
        viewer_count:
          data.viewer_count ?? 0,
      };

    });

  }

} catch (error) {

  console.warn(
    "DroneStream: viewer count error:",
    error
  );

}

}

// ----------------------------------------------------------

// Get stream telemetry
// ----------------------------------------------------------

async function getTelemetry() {
try {
const response = await fetch(
`${API_URL}/api/admin/dashboard`,
{
credentials: "include",
}
);

  if (!response.ok) {
    return;
  }

  const data = await response.json();

  if (data.success) {
    setTelemetry(data);
  }
} catch (error) {
  console.warn(
    "DroneStream: telemetry error:",
    error
  );
}

}

// ----------------------------------------------------------
// Create stream
// ----------------------------------------------------------

async function createStream() {

setLoading(true);
setMessage("");
setViewerLink("");

try {

  const response = await fetch(
    `${API_URL}/api/streams/create`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {
    setStream(data.stream);
    setViewerSessions([]);
    setViewerLink("");
    try {
      sessionStorage.removeItem("dronestream_viewer_link");
    } catch {
      // ignore
    }

    setMessage(
      "Stream created successfully."
    );

  } else {

    setMessage(
      data.message ||
      "Failed to create stream."
    );

  }

} catch {

  setMessage(
    "Failed to create stream."
  );

} finally {

  setLoading(false);

}

}

// ----------------------------------------------------------
// Start stream
// ----------------------------------------------------------

async function startStream() {

setLoading(true);
setMessage("");

try {

  const response = await fetch(
    `${API_URL}/api/streams/start`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {

    setStream({
      ...(data.stream || {}),
      status: data.stream?.status || "live",
    });

    if (data.recording && data.recording.active) {
      setDashboardRecording(data.recording);
    }

    setMessage(
      "Stream is now live."
    );

    getStreamStatus();
    getTelemetry();

  } else {

    setMessage(
      data.message ||
      "Failed to start stream."
    );

  }

} catch {

  setMessage(
    "Failed to start stream."
  );

} finally {

  setLoading(false);

}

}

// ----------------------------------------------------------
// Stop stream
// ----------------------------------------------------------

async function stopStream() {

setLoading(true);
setMessage("");

try {

  const response = await fetch(
    `${API_URL}/api/streams/stop`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {

    setStream({
      ...(data.stream || {}),
      status: data.stream?.status || "offline",
    });
    setDashboardRecording(null);

    setMessage(
      "Stream stopped."
    );

  } else {

    setMessage(
      data.message ||
      "Failed to stop stream."
    );

  }

} catch {

  setMessage(
    "Failed to stop stream."
  );

} finally {

  setLoading(false);

}

}

// ----------------------------------------------------------
// Generate viewer link
// ----------------------------------------------------------

async function generateViewerLink() {
  setLoading(true);
  setMessage("");

  try {
    const minutes =
      linkExpiryMinutes === "" ? null : Number(linkExpiryMinutes);
    const response = await fetch(
      `${API_URL}/api/streams/viewer-link`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expires_in_minutes:
            minutes && minutes > 0 ? minutes : null,
          password:
            linkPassword && linkPassword.trim()
              ? linkPassword.trim()
              : null,
        }),
      }
    );

    setLinkPassword("");

    const data = await response.json();

    if (data.success) {
      const link =
        `${window.location.origin}` +
        `${data.viewer_path}`;
      setViewerLink(link);
      try {
        sessionStorage.setItem("dronestream_viewer_link", link);
      } catch {
        // ignore
      }
      setMessage(
        data.expires_at
          ? `Secure viewer link generated (expires ${new Date(data.expires_at).toLocaleString()}).`
          : "Secure viewer link generated (no expiry)."
      );
    } else {
      setMessage(
        data.message || "Failed to generate viewer link."
      );
    }
  } catch (error) {
    setMessage("Unable to generate viewer link.");
  } finally {
    setLoading(false);
  }
}

async function revokeViewerLink() {
  setLoading(true);
  setMessage("");
  try {
    const response = await fetch(
      `${API_URL}/api/streams/viewer-link/revoke`,
      {
        method: "POST",
        credentials: "include",
      }
    );
    const data = await response.json();
    if (data.success) {
        setViewerLink("");
      try {
        sessionStorage.removeItem("dronestream_viewer_link");
      } catch {
        // ignore
      }
      setMessage(data.message || "Viewer link revoked.");
    } else {
      setMessage(data.message || "Failed to revoke link.");
    }
  } catch (error) {
    setMessage("Unable to revoke viewer link.");
  } finally {
    setLoading(false);
  }
}

// ----------------------------------------------------------
// Start recording
// ----------------------------------------------------------

async function startRecording() {

setRecordingActionLoading(true);
setMessage("");

try {

  const response = await fetch(
    `${API_URL}/api/admin/recording/start`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {

    setDashboardRecording(data.recording);

    setMessage(
      "Recording started."
    );

  } else {

    setMessage(
      data.message ||
      "Failed to start recording."
    );

  }

} catch {

  setMessage(
    "Failed to start recording."
  );

} finally {

  setRecordingActionLoading(false);

}

}

// ----------------------------------------------------------
// Stop recording
// ----------------------------------------------------------

async function stopRecording() {

setRecordingActionLoading(true);
setMessage("");

try {

  const response = await fetch(
    `${API_URL}/api/admin/recording/stop`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {

    setDashboardRecording(null);

    setMessage(
      "Recording stopped."
    );

  } else {

    setMessage(
      data.message ||
      "Failed to stop recording."
    );

  }

} catch {

  setMessage(
    "Failed to stop recording."
  );

} finally {

  setRecordingActionLoading(false);

}

}

// ----------------------------------------------------------
// Capture screenshot
// ----------------------------------------------------------

async function captureScreenshot() {

setScreenshotActionLoading(true);
setMessage("");

try {

  const response = await fetch(
    `${API_URL}/api/admin/screenshot/capture`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {

    setMessage(
      "Screenshot captured."
    );

  } else {

    setMessage(
      data.message ||
      "Failed to capture screenshot."
    );

  }

} catch {

  setMessage(
    "Failed to capture screenshot."
  );

} finally {

  setScreenshotActionLoading(false);

}

}

// ----------------------------------------------------------
// Open viewer
// ----------------------------------------------------------

function openViewer() {
  if (!viewerLink) {
    return;
  }
  window.open(viewerLink, "_blank");
}

function openProjector() {
  const url = `${window.location.origin}/admin/projector`;
  window.open(url, "_blank", "noopener,noreferrer");
}

// ----------------------------------------------------------
// Initial dashboard loading
// ----------------------------------------------------------

useEffect(() => {
  getStreamStatus();
  getViewerCount();
  getTelemetry();

  setLinkPassword("");
  setLinkExpiryMinutes("");

  try {
    const saved = sessionStorage.getItem("dronestream_viewer_link");
    if (saved) {
      setViewerLink(saved);
    }
  } catch {
    // ignore
  }
}, []);


// ----------------------------------------------------------
// Keep stream status, telemetry and viewers updated
// ----------------------------------------------------------

useEffect(() => {

const interval =
  setInterval(() => {
    getStreamStatus();
    getTelemetry();
    getViewerCount();
  }, 3000);

return () => {
  clearInterval(interval);
};

}, []);

const isLive =
String(stream?.status || "").toLowerCase() === "live" ||
String(telemetry?.stream?.status || "").toLowerCase() === "live";

const currentStreamSessions =
viewerSessions.filter(
(session) =>
session.stream_id === stream?.id
);

const activeViewerSessions =
currentStreamSessions.filter(
(session) =>
session.status === "watching"
);

return ( <div className="app">

  <AdminHeader
    isLive={isLive}
  />


  <AdminNavigation
    currentPage="dashboard"
    navigate={navigate}
  />


  <main className="dashboard">

    {/* ================================================== */}
    {/* HERO */}
    {/* ================================================== */}

    <section className="hero hero-with-bg">

      <div className="hero-copy">

        <p className="eyebrow">
          ADMIN CONTROL CENTER
        </p>

        <h1>
          Control your
          <br />
          <span>
            live drone stream.
          </span>
        </h1>

        <p className="hero-text">
          Manage your aerial broadcast,
          monitor viewers and control the
          stream from one secure dashboard.
        </p>

      </div>


      <div
        className={`live-card ${
          isLive ? "active" : ""
        }`}
      >

        <div className="live-card-header">

          <span>
            STREAM STATUS
          </span>

          <span
            className={`status-pill ${
              isLive ? "live" : ""
            }`}
          >
            {stream?.status?.toUpperCase() ||
              "OFFLINE"}
          </span>

        </div>


        <AdminLivePreview
          isLive={isLive}
        />


        <div
          className="dashboard-media-bar"
          style={{
            display: "flex",
            gap: "8px",
            padding: "12px",
            borderTop: "1px solid #1b202a",
            background: "#080b10",
            width: "100%",
            boxSizing: "border-box",
          }}
        >

          <button
            type="button"
            className="viewer-recording-button"
            onClick={
              dashboardRecording
                ? stopRecording
                : startRecording
            }
            disabled={
              recordingActionLoading ||
              !isLive
            }
            style={{
              flex: 1,
              minHeight: "44px",
              padding: "12px 10px",
              border: "1px solid #354052",
              borderRadius: "8px",
              background: isLive ? "#151a23" : "#0d1117",
              color: "#e7ebf1",
              fontSize: "11px",
              fontWeight: 800,
              letterSpacing: "0.06em",
              cursor: isLive ? "pointer" : "not-allowed",
              opacity: isLive ? 1 : 0.45,
            }}
          >
            {recordingActionLoading
              ? (dashboardRecording
                  ? "STOPPING..."
                  : "STARTING...")
              : (dashboardRecording
                  ? "⏹ STOP RECORDING"
                  : "🔴 RECORD")}
          </button>

          <button
            type="button"
            className="viewer-screenshot-button"
            onClick={captureScreenshot}
            disabled={
              screenshotActionLoading ||
              !isLive
            }
            style={{
              flex: 1,
              minHeight: "44px",
              padding: "12px 10px",
              border: "1px solid #354052",
              borderRadius: "8px",
              background: isLive ? "#151a23" : "#0d1117",
              color: "#e7ebf1",
              fontSize: "11px",
              fontWeight: 800,
              letterSpacing: "0.06em",
              cursor: isLive ? "pointer" : "not-allowed",
              opacity: isLive ? 1 : 0.45,
            }}
          >
            {screenshotActionLoading
              ? "CAPTURING..."
              : "📸 SCREENSHOT"}
          </button>

        </div>

        {dashboardRecording && (

          <p className="dashboard-recording-status">
            ● Recording in progress
            {dashboardRecording.filename
              ? ` — ${dashboardRecording.filename}`
              : ""}
          </p>

        )}


        <div className="stream-stats">

          <div>

            <span>
              VIEWERS
            </span>

            <strong>
              {activeViewerSessions.length}
            </strong>

          </div>


          <div>

            <span>
              STREAM ID
            </span>

            <strong>

              {stream?.id
                ? `${stream.id.substring(
                    0,
                    12
                  )}...`
                : "Not created"}

            </strong>

          </div>

        </div>

      </div>

    </section>


    {/* ================================================== */}
    {/* STREAM CONTROLS */}
    {/* ================================================== */}

    <section className="controls-section">

      <div className="section-title">

        <p className="eyebrow">
          STREAM MANAGEMENT
        </p>

        <h2>
          Broadcast controls
        </h2>

      </div>


      <div className="control-grid">

        <button
          className="control-button create"
          onClick={createStream}
          disabled={loading}
        >

          <span className="button-icon">
            ＋
          </span>

          <span>

            <strong>
              Create Stream
            </strong>

            <small>
              Generate a new secure stream
            </small>

          </span>

        </button>


        <button
          className="control-button start"
          onClick={startStream}
          disabled={
            loading ||
            !stream?.id ||
            isLive
          }
        >

          <span className="button-icon">
            ▶
          </span>

          <span>

            <strong>
              Go Live
            </strong>

            <small>
              Begin live broadcasting
            </small>

          </span>

        </button>


        <button
          className="control-button stop"
          onClick={stopStream}
          disabled={
            loading ||
            !stream?.id ||
            !isLive
          }
        >

          <span className="button-icon">
            ■
          </span>

          <span>

            <strong>
              Stop Stream
            </strong>

            <small>
              End the live broadcast
            </small>

          </span>

        </button>

                <button
          className="control-button start"
          onClick={openProjector}
          disabled={!isLive}
        >
          <span className="button-icon">
            ⛶
          </span>
          <span>
            <strong>
              Projector mode
            </strong>
            <small>
              Fullscreen clean live view
            </small>
          </span>
        </button>

        {message && (
        <div className="message" style={{ marginTop: 16, marginBottom: 8 }}>
          {message}
        </div>
      )}

      </div>


      {/* ================================================== */}
      {/* VIEWER ACCESS */}
      {/* ================================================== */}

      <div className="viewer-access">

        <div>

          <p className="eyebrow">
            SECURE VIEWER ACCESS
          </p>

          <h2>
            Share your broadcast
          </h2>

          <p>
            Generate a secure link that
            allows authorized viewers to
            access this stream.
          </p>

        </div>


        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          <label style={{ fontSize: 12, color: "#9aa7b8" }}>
            Expires (minutes)
            <input
              type="number"
              min="1"
              placeholder="Never"
              value={linkExpiryMinutes}
              onChange={(e) => setLinkExpiryMinutes(e.target.value)}
              autoComplete="off"
              style={{
                marginLeft: 8,
                width: 80,
                padding: "6px 8px",
                borderRadius: 6,
                border: "1px solid #354052",
                background: "#121821",
                color: "#d9dfe8",
                WebkitTextFillColor: "#d9dfe8",
                boxShadow: "0 0 0 1000px #121821 inset",
              }}
            />
          </label>

          <label style={{ fontSize: 12, color: "#9aa7b8" }}>
            Password (optional)
            <input
              type="text"
              name="dronestream-viewer-link-password"
              placeholder="None (leave empty)"
              value={linkPassword}
              onChange={(e) => setLinkPassword(e.target.value)}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              style={{
                marginLeft: 8,
                width: 160,
                padding: "6px 8px",
                borderRadius: 6,
                border: "1px solid #354052",
                background: "#121821",
                color: "#d9dfe8",
                WebkitTextFillColor: "#d9dfe8",
                boxShadow: "0 0 0 1000px #121821 inset",
              }}
            />
          </label>

          <button
            className="generate-link-button"
            onClick={generateViewerLink}
            disabled={loading || !stream?.id}
          >
            🔗 Generate Viewer Link
          </button>

          <button
            className="generate-link-button"
            onClick={revokeViewerLink}
            disabled={loading || !stream?.id}
            style={{ background: "#3a1515", borderColor: "#6b2a2a" }}
          >
            ✕ Revoke Link
          </button>
        </div>

      </div>


      {viewerLink && (

        <div className="viewer-link-box">

          <div>

            <span>
              SECURE VIEWER LINK
            </span>

            <strong>
              {viewerLink}
            </strong>

          </div>

          <button
            onClick={openViewer}
          >
            Open Viewer
          </button>

          <div className="admin-viewer-share-actions">
            <button
              onClick={() => navigator.clipboard.writeText(viewerLink).then(() => setMessage("Viewer link copied."))}
            >
              Copy
            </button>
            <a
              href={`https://wa.me/?text=${encodeURIComponent(viewerLink)}`}
              target="_blank"
              rel="noreferrer"
            >
              WhatsApp
            </a>
            <a
              href={`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(viewerLink)}`}
              target="_blank"
              rel="noreferrer"
            >
              Facebook
            </a>
            <a
              href={`https://t.me/share/url?url=${encodeURIComponent(viewerLink)}`}
              target="_blank"
              rel="noreferrer"
            >
              Telegram
            </a>
            <a
              href={`https://twitter.com/intent/tweet?url=${encodeURIComponent(viewerLink)}`}
              target="_blank"
              rel="noreferrer"
            >
              X
            </a>
            {navigator.share && (
              <button
                onClick={() => navigator.share({ title: "DroneStream live feed", url: viewerLink }).catch(() => {})}
              >
                More
              </button>
            )}
          </div>

        </div>

      )}


    </section>

      {/* ================================================== */}
    {/* STREAM TELEMETRY */}
    {/* ================================================== */}

    <section
      style={{
        marginTop: "32px",
      }}
    >

      <div className="section-title">

        <p className="eyebrow">
          STREAM TELEMETRY
        </p>

        <h2>
          Live system health
        </h2>

      </div>


      <div
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(180px, 1fr))",
          gap: "14px",
          marginTop: "20px",
        }}
      >

        {/* STREAM STATUS */}

        <div className="info-card">

          <span className="info-label">
            STREAM STATUS
          </span>

          <strong>
            {telemetry?.stream?.status
              ?.toUpperCase() ||
              stream?.status?.toUpperCase() ||
              "OFFLINE"}
          </strong>

          <p>
            Current broadcast state.
          </p>

        </div>


        {/* VIEWERS */}

        <div className="info-card">

          <span className="info-label">
            ACTIVE VIEWERS
          </span>

          <strong>
            {telemetry?.stream?.viewer_count ??
              activeViewerSessions.length}
          </strong>

          <p>
            Currently connected viewers.
          </p>

        </div>


        {/* UPTIME */}

        <div className="info-card">

          <span className="info-label">
            STREAM UPTIME
          </span>

          <strong>
            {formatDuration(
              telemetry?.stream?.uptime_seconds
            )}
          </strong>

          <p>
            Time since broadcasting started.
          </p>

        </div>


        {/* SOURCE */}

        <div className="info-card">

          <span className="info-label">
            MEDIA SOURCE
          </span>

          <strong>
            {telemetry?.source?.running
              ? "FFmpeg Running"
              : "Source Offline"}
          </strong>

          <p>
            Active media input status.
          </p>

        </div>


        {/* WEBRTC */}

        <div className="info-card">

          <span className="info-label">
            WEBRTC CONNECTIONS
          </span>

          <strong>
            {telemetry?.webrtc
              ?.active_connections ?? 0}
          </strong>

          <p>
            Active browser connections.
          </p>

        </div>


        {/* RESOLUTION */}

        <div className="info-card">

          <span className="info-label">
            VIDEO QUALITY
          </span>

          <strong>
            {telemetry?.source?.running
              ? (telemetry?.source?.resolution || "1280 × 720")
              : "—"}
          </strong>

          <p>
            Current configured resolution.
          </p>

        </div>


        {/* FPS */}

        <div className="info-card">

          <span className="info-label">
            FRAME RATE
          </span>

          <strong>
            {telemetry?.source?.running
              ? "30 FPS"
              : "—"}
          </strong>

          <p>
            Current configured frame rate.
          </p>

        </div>


        {/* HEALTH */}

        <div className="info-card">

          <span className="info-label">
            STREAM HEALTH
          </span>

          <strong>
            {telemetry?.source?.running &&
            telemetry?.stream?.status ===
              "live"
              ? "HEALTHY"
              : telemetry?.stream?.status ===
                  "live"
                ? "DEGRADED"
                : "OFFLINE"}
          </strong>

          <p>
            Backend media and stream state.
          </p>

        </div>

      </div>

    </section>


    {/* ================================================== */}
    {/* INFORMATION */}
    {/* ================================================== */}

    <section className="information-grid">

      <div className="info-card">

        <span className="info-label">
          STREAM ID
        </span>

        <strong className="stream-id">
          {stream?.id ||
            "No stream created"}
        </strong>

        <p>
          Internal identifier for this
          broadcast.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          VIEWER ACCESS
        </span>

        <strong>
          {isLive
            ? "Broadcast available"
            : "Broadcast unavailable"}
        </strong>

        <p>
          Viewer links are protected by
          server-side authorization.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          SYSTEM
        </span>

        <strong>
          DroneStream API
        </strong>

        <p>
          Connected to the local FastAPI
          streaming backend.
        </p>

      </div>

    </section>

  </main>


  <footer>

    <span>
      DRONESTREAM
    </span>

    <span>
      Secure streaming platform · v0.1.0
    </span>

  </footer>

</div>

);
}

// ============================================================
// VIEWER MONITORING PAGE
// ============================================================

function ViewerMonitoringPage({ navigate }) {

const [stream, setStream] = useState(null);
const [viewerSessions, setViewerSessions] = useState([]);
const [viewerLoading, setViewerLoading] = useState(false);
const [recordingPermissions, setRecordingPermissions] = useState([]);
const [recordingActionLoading, setRecordingActionLoading] = useState(null);
const [screenshotPermissions, setScreenshotPermissions] = useState([]);
const [screenshotActionLoading, setScreenshotActionLoading] = useState(null);
const [kickLoading, setKickLoading] = useState(null);

// ----------------------------------------------------------
// Get stream status
// ----------------------------------------------------------

async function getStreamStatus() {

try {

  const response = await fetch(
    `${API_URL}/api/streams/status`,
    {
      credentials: "include",
    }
  );

  const data = await response.json();

  if (data.success) {
    setStream(data.stream);
  }

} catch (error) {

  console.warn(
    "DroneStream: stream status error:",
    error
  );

}

}

// ----------------------------------------------------------
// Get viewer sessions
// ----------------------------------------------------------

async function getViewerSessions() {

try {

  setViewerLoading(true);

  const response = await fetch(
    `${API_URL}/api/viewer/sessions`,
    {
      credentials: "include",
    }
  );
  if (!response.ok) {
    throw new Error(
      "Unable to retrieve viewer sessions."
    );
  }

  const data = await response.json();

  if (data.success) {

    setViewerSessions(
      data.sessions || []
    );

    setStream((currentStream) => {

      if (!currentStream) {
        return currentStream;
      }

      return {
        ...currentStream,
        viewer_count:
          data.viewer_count ?? 0,
      };

    });

  }

} catch (error) {

  console.warn(
    "DroneStream: viewer monitoring error:",
    error
  );

} finally {

  setViewerLoading(false);

}

}


  async function clearEndedViewers() {
    if (
      !window.confirm(
        "Remove all ended / disconnected / kicked viewers from the list? Active watchers are kept."
      )
    ) {
      return;
    }
    try {
      const response = await fetch(
        `${API_URL}/api/admin/viewer-sessions/ended`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );
      const data = await response.json();
      if (!data.success) {
        alert(data.message || "Failed to clear ended viewers.");
        return;
      }
      await getViewerSessions();
    } catch {
      alert("Failed to clear ended viewers.");
    }
  }

// ----------------------------------------------------------
// Kick viewer sessions
// ----------------------------------------------------------

async function kickViewer(sessionId) {
  if (!window.confirm("Kick this viewer off the stream?")) {
    return;
  }

  setKickLoading(sessionId);

  try {
    const response = await fetch(
      `${API_URL}/api/viewer/sessions/${encodeURIComponent(sessionId)}/kick`,
      {
        method: "POST",
        credentials: "include",
      }
    );

    const data = await response.json();

    if (data.success) {
      await getViewerSessions();
    } else {
      alert(data.message || "Failed to kick viewer.");
    }
  } catch (error) {
    alert("Unable to kick viewer.");
  } finally {
    setKickLoading(null);
  }
}

// ----------------------------------------------------------
// Get recording permissions
// ----------------------------------------------------------

async function getRecordingPermissions() {

try {

  const response = await fetch(
    `${API_URL}/api/admin/recording-permissions`,
    {
      credentials: "include",
    }
  );

  if (!response.ok) {
    throw new Error(
      "Unable to retrieve recording permissions."
    );
  }

  const data = await response.json();

  if (data.success) {

    setRecordingPermissions(
      data.viewers || []
    );

  }

} catch (error) {

  console.warn(
    "DroneStream: recording permission error:",
    error
  );

}

}

// ----------------------------------------------------------
// Get screenshot permissions
// ----------------------------------------------------------

async function getScreenshotPermissions() {

try {

  const response = await fetch(
    `${API_URL}/api/admin/screenshot-permissions`,
    {
      credentials: "include",
    }
  );

  if (!response.ok) {
    throw new Error(
      "Unable to retrieve screenshot permissions."
    );
  }

  const data = await response.json();

  if (data.success) {

    setScreenshotPermissions(
      data.viewers || []
    );

  }

} catch (error) {

  console.warn(
    "DroneStream: screenshot permission error:",
    error
  );

}

}

// ----------------------------------------------------------
// Change screenshot permission
// ----------------------------------------------------------

async function changeScreenshotPermission(
viewerSessionId,
currentlyAllowed
) {

if (!viewerSessionId) {
  return;
}

try {

  setScreenshotActionLoading(
    viewerSessionId
  );

  const action = currentlyAllowed
    ? "revoke"
    : "grant";

  const response = await fetch(
    `${API_URL}/api/admin/screenshot-permissions/${viewerSessionId}/${action}`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (!response.ok || !data.success) {

    throw new Error(
      data.message ||
      "Unable to change screenshot permission."
    );

  }

  await getScreenshotPermissions();

} catch (error) {

  console.error(
    "DroneStream: screenshot permission change error:",
    error
  );

} finally {

  setScreenshotActionLoading(null);

}

}

// ----------------------------------------------------------
// Change recording permission
// ----------------------------------------------------------

async function changeRecordingPermission(
viewerSessionId,
currentlyAllowed
) {

if (!viewerSessionId) {
  return;
}

try {

  setRecordingActionLoading(
    viewerSessionId
  );

  const action = currentlyAllowed
    ? "revoke"
    : "grant";

  const response = await fetch(
    `${API_URL}/api/admin/recording-permissions/${viewerSessionId}/${action}`,
    {
      method: "POST",
      credentials: "include",
    }
  );

  const data = await response.json();

  if (!response.ok || !data.success) {

    throw new Error(
      data.message ||
      "Unable to change recording permission."
    );

  }

  await getRecordingPermissions();

} catch (error) {

  console.error(
    "DroneStream: recording permission change error:",
    error
  );

} finally {

  setRecordingActionLoading(null);

}

}

// ----------------------------------------------------------
// Initial loading
// ----------------------------------------------------------

useEffect(() => {
  getStreamStatus();
  getViewerSessions();

  const interval = setInterval(() => {
    getStreamStatus();
    getViewerSessions();
  }, 3000);

  return () => clearInterval(interval);
}, []);

// ----------------------------------------------------------
// Automatic monitoring refresh
// ----------------------------------------------------------

useEffect(() => {

const interval =
  setInterval(() => {

    getViewerSessions();
    getRecordingPermissions();
    getScreenshotPermissions();

  }, 3000);


return () => {

  clearInterval(interval);

};

}, []);

// ----------------------------------------------------------
// Check recording permission
// ----------------------------------------------------------

function isRecordingAllowed(sessionId) {

const permission = recordingPermissions.find(
  (item) =>
    item.session_id === sessionId
);

return permission?.recording_allowed === true;

}

// ----------------------------------------------------------
// Check screenshot permission
// ----------------------------------------------------------

function isScreenshotAllowed(sessionId) {

const permission = screenshotPermissions.find(
  (item) =>
    item.session_id === sessionId
);

return permission?.screenshot_allowed === true;

}

const currentStreamSessions =
viewerSessions.filter(
(session) =>
session.stream_id === stream?.id
);

const activeViewerSessions =
currentStreamSessions.filter(
(session) =>
session.status === "watching"
);

const isLive =
stream?.status === "live";

return ( <div className="app">

  <AdminHeader
    isLive={isLive}
  />


  <AdminNavigation
    currentPage="viewers"
    navigate={navigate}
  />


  <main className="dashboard">

    {/* ================================================== */}
    {/* PAGE HEADER */}
    {/* ================================================== */}

    <section className="viewer-monitoring-page-header">

      <p className="eyebrow">
        LIVE VIEWER MONITORING
      </p>

      <h1>
        Viewer activity
      </h1>

      <p className="hero-text">
        Monitor viewers currently connected
        to this broadcast and review their
        connection information.
      </p>

    </section>


    {/* ================================================== */}
    {/* MONITORING SUMMARY */}
    {/* ================================================== */}

    <section className="viewer-monitoring-summary">

      <div className="monitor-stat">

        <span>
          ACTIVE VIEWERS
        </span>

        <strong>
          {activeViewerSessions.length}
        </strong>

      </div>


      <div className="monitor-stat">

        <span>
          TOTAL SESSIONS
        </span>

        <strong>
          {currentStreamSessions.length}
        </strong>

      </div>


      <div className="monitor-stat">

        <span>
          MONITOR STATUS
        </span>

        <strong>
          {viewerLoading
            ? "UPDATING..."
            : "LIVE"}
        </strong>

      </div>

    </section>


    {/* ================================================== */}
    {/* CURRENT STREAM */}
    {/* ================================================== */}

    <section className="viewer-monitoring-stream-card">

      <span className="info-label">
        CURRENT STREAM
      </span>

      <strong>
        {stream?.id || "No stream created"}
      </strong>

      <span
        className={`status-pill ${
          isLive ? "live" : ""
        }`}
      >
        {stream?.status?.toUpperCase() ||
          "OFFLINE"}
      </span>

    </section>


    {/* ================================================== */}
    {/* VIEWER TABLE */}
    {/* ================================================== */}

    <section className="viewer-monitoring">

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <strong style={{ fontSize: 13, letterSpacing: "0.06em" }}>
          VIEWER SESSIONS
        </strong>
        <button
          type="button"
          className="recording-action-button"
          onClick={clearEndedViewers}
        >
          CLEAR ENDED
        </button>
      </div>

      <div className="viewer-table-container">

        {currentStreamSessions.length === 0 ? (

          <div className="no-viewers">

            <div className="no-viewers-icon">
              ◌
            </div>

            <strong>
              No viewers yet
            </strong>

            <span>
              Viewer activity will appear
              here when someone opens the
              secure broadcast link.
            </span>

          </div>

        ) : (

          <div className="viewer-table">

            <div className="viewer-table-header">

              <span>
                STATUS
              </span>

              <span>
                DEVICE
              </span>

              <span>
                BROWSER
              </span>

              <span>
                IP ADDRESS
              </span>

              <span>
                LOCATION
              </span>

              <span>
                CONNECTED
              </span>

              <span>
                DURATION
              </span>

              <span>
                RECORDING
              </span>

              <span>
                SCREENSHOT
              </span>

              <span>
                ACTIONS
              </span>

            </div>


            {currentStreamSessions.map(
              (session) => (

                <div
                  className="viewer-table-row"
                  key={
                    session.session_id
                  }
                >

                  <span>

                    <span
                      className={`viewer-status-indicator ${
                        session.status ===
                        "watching"
                          ? "active"
                          : "ended"
                      }`}
                    ></span>

                    {formatViewerStatus(session.status)}

                  </span>


                  <span>
                    {getDeviceType(
                      session.user_agent
                    )}
                  </span>


                  <span>
                    {getBrowserName(
                      session.user_agent
                    )}
                  </span>


                  <span>
                    {session.ip_address ||
                      "Unknown"}
                  </span>


                  <span>
                    {session.city || session.region || session.country
                      ? [session.city, session.region, session.country]
                          .filter(Boolean)
                          .join(", ")
                      : "—"}
                  </span>


                  <span>
                    {formatConnectionTime(
                      session.connected_at
                    )}
                  </span>


                  <span>
                    {formatDuration(
                      session.duration_seconds
                    )}
                  </span>


                  {/* ================================================== */}
                  {/* RECORDING PERMISSION */}
                  {/* ================================================== */}

                  <span>

                    {(() => {

                      const allowed =
                        isRecordingAllowed(
                          session.session_id
                        );

                      const permission =
                        recordingPermissions.find(
                          (item) =>
                            item.session_id ===
                            session.session_id
                        );

                      const loading =
                        recordingActionLoading ===
                        permission?.viewer_session_id;


                      if (
                        session.status !==
                        "watching"
                      ) {

                        return (
                          <span className="recording-status-disabled">
                            Unavailable
                          </span>
                        );

                      }


                      return (
                        <button
                          className={`recording-permission-button ${
                            allowed
                              ? "revoke"
                              : "grant"
                          }`}
                          disabled={
                            loading ||
                            !permission?.viewer_session_id
                          }
                          onClick={() =>
                            changeRecordingPermission(
                              permission.viewer_session_id,
                              allowed
                            )
                          }
                        >

                          {loading
                            ? "UPDATING..."
                            : allowed
                              ? "REVOKE"
                              : "ALLOW"}

                        </button>
                      );

                    })()}

                  </span>

                  {/* ================================================== */}
                  {/* SCREENSHOT PERMISSION */}
                  {/* ================================================== */}

                  <span>

                    {(() => {

                      const allowed =
                        isScreenshotAllowed(
                          session.session_id
                        );

                      const permission =
                        screenshotPermissions.find(
                          (item) =>
                            item.session_id ===
                            session.session_id
                        );

                      const loading =
                        screenshotActionLoading ===
                        permission?.viewer_session_id;


                      if (
                        session.status !==
                        "watching"
                      ) {

                        return (
                          <span className="recording-status-disabled">
                            Unavailable
                          </span>
                        );

                      }


                      return (
                        <button
                          className={`recording-permission-button ${
                            allowed
                              ? "revoke"
                              : "grant"
                          }`}
                          disabled={
                            loading ||
                            !permission?.viewer_session_id
                          }
                          onClick={() =>
                            changeScreenshotPermission(
                              permission.viewer_session_id,
                              allowed
                            )
                          }
                        >

                          {loading
                            ? "UPDATING..."
                            : allowed
                              ? "REVOKE"
                              : "ALLOW"}

                        </button>
                      );

                    })()}

                  </span>

                  <span>
                    {session.status === "watching" ? (
                      <button
                        className="recording-permission-button revoke"
                        disabled={kickLoading === session.session_id}
                        onClick={() =>
                          kickViewer(session.session_id)
                        }
                      >
                        {kickLoading === session.session_id
                          ? "..."
                          : "KICK"}
                      </button>
                    ) : (
                      <span className="recording-status-disabled">
                        —
                      </span>
                    )}
                  </span>

                </div>

              )
            )}

          </div>

        )}

      </div>

    </section>


    {/* ================================================== */}
    {/* MONITORING INFORMATION */}
    {/* ================================================== */}

    <section className="information-grid">

      <div className="info-card">

        <span className="info-label">
          ACTIVE VIEWERS
        </span>

        <strong>
          {activeViewerSessions.length}
        </strong>

        <p>
          Viewers currently connected to
          the active broadcast.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          SESSION TRACKING
        </span>

        <strong>
          Enabled
        </strong>

        <p>
          Connection and disconnection
          events are being tracked.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          REFRESH RATE
        </span>

        <strong>
          3 seconds
        </strong>

        <p>
          Viewer monitoring automatically
          refreshes every three seconds.
        </p>

      </div>

    </section>

  </main>


  <footer>

    <span>
      DRONESTREAM
    </span>

    <span>
      Secure streaming platform · v0.1.0
    </span>

  </footer>

</div>

);
}


// ============================================================
// RECORDINGS PAGE
// ============================================================

function RecordingsPage({ navigate }) {

const [stream, setStream] = useState(null);
const [recordings, setRecordings] = useState([]);
const [recordingsLoading, setRecordingsLoading] = useState(false);
const [playingRecording, setPlayingRecording] = useState(null);
const [message, setMessage] = useState("");
const playerPanelRef = React.useRef(null);

useEffect(() => {
  if (playingRecording && playerPanelRef.current) {
    playerPanelRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}, [playingRecording]);

  async function deleteRecording(rec) {
    if (!rec?.id) return;
    if (!window.confirm(`Delete recording "${rec.file_name}"? This cannot be undone.`)) {
      return;
    }
    try {
      const response = await fetch(
        `${API_URL}/api/admin/recordings/${rec.id}`,
        { method: "DELETE", credentials: "include" }
      );
      const data = await response.json();
      if (!data.success) {
        setMessage(data.message || "Failed to delete recording.");
        return;
      }
      setMessage(data.message || "Recording deleted.");
      if (playingRecording?.id === rec.id) {
        setPlayingRecording(null);
      }
      getRecordingHistory();
    } catch {
      setMessage("Failed to delete recording.");
    }
  }

  async function clearAllRecordings() {
    if (
      !window.confirm(
        "Delete ALL recordings and files? This cannot be undone."
      )
    ) {
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/admin/recordings`, {
        method: "DELETE",
        credentials: "include",
      });
      const data = await response.json();
      if (!data.success) {
        setMessage(data.message || "Failed to clear recordings.");
        return;
      }
      setMessage(data.message || "All recordings deleted.");
      setPlayingRecording(null);
      getRecordingHistory();
    } catch {
      setMessage("Failed to clear recordings.");
    }
  }

// ----------------------------------------------------------
// Get current stream status
// ----------------------------------------------------------

async function getStreamStatus() {

  try {

    const response = await fetch(
      `${API_URL}/api/streams/status`,
      {
        credentials: "include",
      }
    );

    if (!response.ok) {
      return;
    }

    const data = await response.json();

    if (data.success) {
      setStream(data.stream);
    }

  } catch (error) {

    console.warn(
      "DroneStream: recording stream status error:",
      error
    );

  }

}

// ----------------------------------------------------------
// Get recording history
// ----------------------------------------------------------

async function getRecordingHistory() {

  try {

    setRecordingsLoading(true);

    const response = await fetch(
      `${API_URL}/api/admin/recordings`,
      {
        credentials: "include",
      }
    );

    if (!response.ok) {
      throw new Error(
        "Unable to retrieve recording history."
      );
    }

    const data = await response.json();

    if (data.success) {

      setRecordings(
        data.recordings || []
      );

    }

  } catch (error) {

    console.warn(
      "DroneStream: recording history error:",
      error
    );

  } finally {

    setRecordingsLoading(false);

  }

}

// ----------------------------------------------------------
// Initial loading
// ----------------------------------------------------------

useEffect(() => {

  getStreamStatus();
  getRecordingHistory();

}, []);

// ----------------------------------------------------------
// Keep stream status updated
// ----------------------------------------------------------

useEffect(() => {

  const interval = setInterval(() => {

    getStreamStatus();

  }, 3000);

  return () => {

    clearInterval(interval);

  };

}, []);

const isLive =
  stream?.status === "live";

return (

<div className="app">

  <AdminHeader
    isLive={isLive}
  />


  <AdminNavigation
    currentPage="recordings"
    navigate={navigate}
  />


  <main className="dashboard">

    {/* ================================================== */}
    {/* PAGE HEADER */}
    {/* ================================================== */}

    <section className="viewer-monitoring-page-header">

      <p className="eyebrow">
        RECORDING LIBRARY
      </p>

      <h1>
        Stream recordings
      </h1>

      <p className="hero-text">
        Review, play and download every
        recording captured from this
        broadcast. Start and stop
        recording from the Dashboard.
      </p>

    </section>


    {/* ================================================== */}
    {/* RECORDING HISTORY */}
    {/* ================================================== */}

    <section className="screenshot-history-section">

      <div className="section-title">

        <p className="eyebrow">
          RECORDING HISTORY
        </p>

        <h2>
          Saved recordings
        </h2>

      </div>


      {playingRecording && (

        <div
          className="recording-player"
          ref={playerPanelRef}
        >

          <div className="recording-player-header">

            <span>
              {playingRecording.file_name}
            </span>

            <button
              type="button"
              onClick={() =>
                setPlayingRecording(null)
              }
            >
              CLOSE
            </button>

          </div>

          <video
            controls
            autoPlay
            src={`${API_URL}/api/admin/recordings/${playingRecording.id}/stream`}
          />

        </div>

      )}


            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <strong style={{ fontSize: 13, letterSpacing: "0.06em" }}>RECORDING HISTORY</strong>
        <button
          type="button"
          className="recording-action-button"
          onClick={clearAllRecordings}
        >
          CLEAR ALL
        </button>
        {message && (
          <span style={{ fontSize: 12, color: "#9aa7b8" }}>{message}</span>
        )}
      </div>


      <div className="screenshot-history">

        {recordingsLoading ? (

          <div className="screenshot-history-empty">

            <strong>
              Loading recording history...
            </strong>

          </div>

        ) : recordings.length === 0 ? (

          <div className="screenshot-history-empty">

            <span className="screenshot-history-icon">
              ◉
            </span>

            <strong>
              No recordings yet
            </strong>

            <span>
              Recordings saved from the live
              broadcast will appear here.
            </span>

          </div>

        ) : (

          <div className="screenshot-history-table">

            <div className="screenshot-history-header">

              <span>
                FILE
              </span>

              <span>
                STREAM
              </span>

              <span>
                DURATION
              </span>

              <span>
                SIZE
              </span>

              <span>
                ENDED
              </span>

              <span>
                CREATED BY
              </span>

              <span>
                ACTIONS
              </span>

            </div>


            {recordings.map((rec) => (

              <div
                className="screenshot-history-row"
                key={rec.id}
              >

                <span
                  className="screenshot-file-name"
                  title={rec.file_name}
                >
                  {rec.file_name}
                </span>


                <span>
                  #{rec.stream_id}
                </span>


                <span>
                  {rec.duration_seconds
                    ? `${rec.duration_seconds.toFixed(1)}s`
                    : "—"}
                </span>


                <span>
                  {rec.file_size_bytes
                    ? `${(
                        rec.file_size_bytes /
                        (1024 * 1024)
                      ).toFixed(2)} MB`
                    : "—"}
                </span>


                <span>
                  {rec.ended_at
                    ? new Date(
                        rec.ended_at
                      ).toLocaleString()
                    : "—"}
                </span>


                <span>
                  {rec.created_by_viewer_session_id
                    ? `VIEWER #${rec.created_by_viewer_session_id}`
                    : rec.created_by_admin_id
                      ? `ADMIN #${rec.created_by_admin_id}`
                      : "AUTO / ADMIN"}
                </span>

                <span className="recording-actions">

                  <button
                    type="button"
                    className="recording-action-button"
                    onClick={() =>
                      setPlayingRecording(rec)
                    }
                  >
                    PLAY
                  </button>

                  <a
                    className="recording-action-button"
                    href={`${API_URL}/api/admin/recordings/${rec.id}/download`}
                  >
                    DOWNLOAD
                  </a>

                  <button
                    type="button"
                    className="recording-action-button"
                    onClick={() => deleteRecording(rec)}
                  >
                    DELETE
                  </button>

                </span>

              </div>

            ))}

          </div>

        )}

      </div>

    </section>


    {/* ================================================== */}
    {/* RECORDING ACCESS */}
    {/* ================================================== */}

    <section className="information-grid">

      <div className="info-card">

        <span className="info-label">
          RECORDING ACCESS
        </span>

        <strong>
          Admin controlled
        </strong>

        <p>
          Recording is started and stopped
          from the Dashboard. Viewer
          permissions are controlled from
          Viewer Monitoring.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          STREAM
        </span>

        <strong>
          {stream?.id ||
            "No stream created"}
        </strong>

        <p>
          Current DroneStream broadcast.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          MEDIA FORMAT
        </span>

        <strong>
          MP4
        </strong>

        <p>
          Completed recordings are stored
          as MP4 video files.
        </p>

      </div>

    </section>

  </main>


  <footer>

    <span>
      DRONESTREAM
    </span>

    <span>
      Secure streaming platform · v0.1.0
    </span>

  </footer>

</div>

);
}

// ============================================================
// SCREENSHOTS PAGE
// ============================================================

function ScreenshotsPage({ navigate }) {

const [stream, setStream] = useState(null);
const [loading, setLoading] = useState(false);
const [message, setMessage] = useState("");
const [error, setError] = useState("");
const [lastScreenshot, setLastScreenshot] = useState(null);
const [screenshots, setScreenshots] = useState([]);
const [screenshotsLoading, setScreenshotsLoading] = useState(false);
const [viewingScreenshot, setViewingScreenshot] = useState(null);
const screenshotPanelRef = React.useRef(null);

useEffect(() => {
  if (viewingScreenshot && screenshotPanelRef.current) {
    screenshotPanelRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}, [viewingScreenshot]);

// ----------------------------------------------------------
// Get current stream status
// ----------------------------------------------------------

async function getStreamStatus() {

  try {

    const response = await fetch(
      `${API_URL}/api/streams/status`,
      {
        credentials: "include",
      }
    );

    if (!response.ok) {
      return;
    }

    const data = await response.json();

    if (data.success) {
      setStream(data.stream);
    }

  } catch (error) {

    console.warn(
      "DroneStream: screenshot stream status error:",
      error
    );

  }

}


  async function deleteScreenshot(shot) {
    if (!shot?.id) return;
    if (!window.confirm(`Delete screenshot "${shot.file_name}"? This cannot be undone.`)) {
      return;
    }
    try {
      const response = await fetch(
        `${API_URL}/api/admin/screenshots/${shot.id}`,
        { method: "DELETE", credentials: "include" }
      );
      const data = await response.json();
      if (!data.success) {
        setMessage(data.message || "Failed to delete screenshot.");
        return;
      }
      setMessage(data.message || "Screenshot deleted.");
      if (viewingScreenshot?.id === shot.id) {
        setViewingScreenshot(null);
      }
      getScreenshotHistory();
    } catch {
      setMessage("Failed to delete screenshot.");
    }
  }

  async function clearAllScreenshots() {
    if (
      !window.confirm(
        "Delete ALL screenshots and files? This cannot be undone."
      )
    ) {
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/admin/screenshots`, {
        method: "DELETE",
        credentials: "include",
      });
      const data = await response.json();
      if (!data.success) {
        setMessage(data.message || "Failed to clear screenshots.");
        return;
      }
      setMessage(data.message || "All screenshots deleted.");
      setViewingScreenshot(null);
      getScreenshotHistory();
    } catch {
      setMessage("Failed to clear screenshots.");
    }
  }


// ----------------------------------------------------------
// Get screenshot history
// ----------------------------------------------------------

async function getScreenshotHistory() {

  try {

    setScreenshotsLoading(true);

    const response = await fetch(
      `${API_URL}/api/admin/screenshots`,
      {
        credentials: "include",
      }
    );

    if (!response.ok) {
      throw new Error(
        "Unable to retrieve screenshot history."
      );
    }

    const data = await response.json();

    if (data.success) {

      setScreenshots(
        data.screenshots || []
      );

    }

  } catch (error) {

    console.warn(
      "DroneStream: screenshot history error:",
      error
    );

  } finally {

    setScreenshotsLoading(false);

  }

}

// ----------------------------------------------------------
// Capture screenshot
// ----------------------------------------------------------

async function captureScreenshot() {

  setLoading(true);
  setMessage("");
  setError("");

  try {

    const response = await fetch(
      `${API_URL}/api/admin/screenshot/capture`,
      {
        method: "POST",
        credentials: "include",
      }
    );

    const data = await response.json();

    if (!response.ok || !data.success) {

      throw new Error(
        data.message ||
        "Unable to capture screenshot."
      );

    }

    setLastScreenshot(
      data.screenshot
    );

    await getScreenshotHistory();

    setMessage(
      "Screenshot captured successfully."
    );

  } catch (error) {

    console.error(
      "DroneStream: screenshot capture error:",
      error
    );

    setError(
      error.message ||
      "Unable to capture screenshot."
    );

  } finally {

    setLoading(false);

  }

}

// ----------------------------------------------------------
// Initial loading
// ----------------------------------------------------------

useEffect(() => {

  getStreamStatus();
  getScreenshotHistory();

}, []);

// ----------------------------------------------------------
// Keep stream status updated
// ----------------------------------------------------------

useEffect(() => {

  const interval = setInterval(() => {

    getStreamStatus();

  }, 3000);

  return () => {

    clearInterval(interval);

  };

}, []);

const isLive =
  stream?.status === "live";

return (

<div className="app screenshots-page">

  <AdminHeader
    isLive={isLive}
  />


  <AdminNavigation
    currentPage="screenshots"
    navigate={navigate}
  />


  <main className="dashboard">

    {/* ================================================== */}
    {/* PAGE HEADER */}
    {/* ================================================== */}

    <section className="viewer-monitoring-page-header">

      <p className="eyebrow">
        SCREENSHOT CONTROL CENTER
      </p>

      <h1>
        Stream screenshots
      </h1>

      <p className="hero-text">
        Review and download every screenshot
        captured from this broadcast. Capture
        a new screenshot from the Dashboard.
      </p>

    </section>


    {/* ================================================== */}
    {/* SCREENSHOT STATUS */}
    {/* ================================================== */}

    <section
      className="viewer-monitoring-summary"
    >

      <div className="monitor-stat">

        <span>
          STREAM STATUS
        </span>

        <strong>
          {stream?.status?.toUpperCase() ||
            "OFFLINE"}
        </strong>

      </div>


      <div className="monitor-stat">

        <span>
          SCREENSHOT CONTROL
        </span>

        <strong>
          ADMIN + PERMITTED VIEWERS
        </strong>

      </div>


      <div className="monitor-stat">

        <span>
          IMAGE FORMAT
        </span>

        <strong>
          PNG
        </strong>

      </div>

    </section>


    {/* ================================================== */}
    {/* SCREENSHOT HISTORY */}
    {/* ================================================== */}

    <section className="screenshot-history-section">

      <div className="section-title">

        <p className="eyebrow">
          SCREENSHOT HISTORY
        </p>

        <h2>
          Captured screenshots
        </h2>

      </div>


      {viewingScreenshot && (

        <div
          className="recording-player"
          ref={screenshotPanelRef}
        >

          <div className="recording-player-header">

            <span>
              {viewingScreenshot.file_name}
            </span>

            <button
              type="button"
              onClick={() =>
                setViewingScreenshot(null)
              }
            >
              CLOSE
            </button>

          </div>

          <img
            src={`${API_URL}/api/admin/screenshots/${viewingScreenshot.id}/view`}
            alt={viewingScreenshot.file_name}
          />

        </div>

      )}


            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <strong style={{ fontSize: 13, letterSpacing: "0.06em" }}>SCREENSHOT HISTORY</strong>
        <button
          type="button"
          className="recording-action-button"
          onClick={clearAllScreenshots}
        >
          CLEAR ALL
        </button>
        {message && (
          <span style={{ fontSize: 12, color: "#9aa7b8" }}>{message}</span>
        )}
      </div>


      <div className="screenshot-history">

        {screenshotsLoading ? (

          <div className="screenshot-history-empty">

            <strong>
              Loading screenshot history...
            </strong>

          </div>

        ) : screenshots.length === 0 ? (

          <div className="screenshot-history-empty">

            <span className="screenshot-history-icon">
              ◉
            </span>

            <strong>
              No screenshots captured
            </strong>

            <span>
              Screenshots captured from the live
              broadcast will appear here.
            </span>

          </div>

        ) : (

          <div className="screenshot-history-table">

            <div className="screenshot-history-header">

              <span>
                FILE
              </span>

              <span>
                STREAM
              </span>

              <span>
                SIZE
              </span>

              <span>
                CAPTURED
              </span>

              <span>
                CREATED BY
              </span>

              <span>
                ACTIONS
              </span>

            </div>

            {screenshots.map((screenshot) => (

              <div
                className="screenshot-history-row"
                key={screenshot.id}
              >

                <span
                  className="screenshot-file-name"
                  title={screenshot.file_name}
                >
                  {screenshot.file_name}
                </span>


                <span>
                  #{screenshot.stream_id}
                </span>


                <span>
                  {screenshot.file_size_bytes
                    ? `${(
                        screenshot.file_size_bytes /
                        1024
                      ).toFixed(1)} KB`
                    : "—"}
                </span>


                <span>
                  {screenshot.captured_at
                    ? new Date(
                        screenshot.captured_at
                      ).toLocaleString()
                    : "—"}
                </span>


                <span>
                  {screenshot.created_by_viewer_session_id
                    ? `VIEWER #${screenshot.created_by_viewer_session_id}`
                    : screenshot.created_by_admin_id
                      ? `ADMIN #${screenshot.created_by_admin_id}`
                      : "—"}
                </span>

                <span className="recording-actions">

                  <button
                    type="button"
                    className="recording-action-button"
                    onClick={() =>
                      setViewingScreenshot(screenshot)
                    }
                  >
                    VIEW
                  </button>

                  <a
                    className="recording-action-button"
                    href={`${API_URL}/api/admin/screenshots/${screenshot.id}/download`}
                  >
                    DOWNLOAD
                  </a>

                  <button
                    type="button"
                    className="recording-action-button"
                    onClick={() => deleteScreenshot(screenshot)}
                  >
                    DELETE
                  </button>

                </span>

              </div>

            ))}

          </div>

        )}

      </div>

    </section>


    {/* ================================================== */}
    {/* SCREENSHOT INFORMATION */}
    {/* ================================================== */}

    <section className="information-grid">

      <div className="info-card">

        <span className="info-label">
          CAPTURE SOURCE
        </span>

        <strong>
          Live DroneStream
        </strong>

        <p>
          Screenshots are captured directly
          from the active media source.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          RESOLUTION
        </span>

        <strong>
          1280 × 720
        </strong>

        <p>
          Screenshots use the current stream
          resolution.
        </p>

      </div>


      <div className="info-card">

        <span className="info-label">
          ACCESS
        </span>

        <strong>
          Admin controlled — viewers require permission        
        </strong>

        <p>
          Only authenticated administrators
          can capture screenshots.
        </p>

      </div>

    </section>

  </main>


  <footer>

    <span>
      DRONESTREAM
    </span>

    <span>
      Secure streaming platform · v0.1.0
    </span>

  </footer>

</div>

);
}

// ============================================================
// SETTINGS PAGE
// ============================================================

function SettingsPage({ navigate }) {

const [stream, setStream] = useState(null);
const [loading, setLoading] = useState(false);
const [saving, setSaving] = useState(false);
const [message, setMessage] = useState("");
const [error, setError] = useState("");

const [settings, setSettings] = useState({
  default_viewer_can_record: false,
  default_viewer_can_screenshot: false,
  auto_record_on_live: false,
  require_viewer_permission: true,
  max_viewer_sessions: 50,
  session_timeout_minutes: 20,
  use_capture_card: false,
  capture_device_name: "USB Video",
});

const isLive =
  String(stream?.status || "").toLowerCase() === "live";

async function getStreamStatus() {
  try {
    const response = await fetch(
      `${API_URL}/api/streams/status`,
      { credentials: "include" }
    );
    if (!response.ok) return;
    const data = await response.json();
    if (data.success) setStream(data.stream);
  } catch (err) {
    console.warn("DroneStream: settings stream status error:", err);
  }
}

async function getSettings() {
  setLoading(true);
  setError("");
  try {
    const response = await fetch(
      `${API_URL}/api/admin/settings`,
      { credentials: "include" }
    );
    if (response.ok) {
      const data = await response.json();
      if (data.success && data.settings) {
        setSettings((prev) => ({ ...prev, ...data.settings }));
      }
    }
  } catch (err) {
    console.warn("DroneStream: settings load error:", err);
  } finally {
    setLoading(false);
  }
}

async function saveSettings(e) {
  if (e) e.preventDefault();
  setSaving(true);
  setMessage("");
  setError("");
  try {
    const response = await fetch(
      `${API_URL}/api/admin/settings`,
      {
        method: "PUT",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
      throw new Error(
        data.message || "Unable to save settings."
      );
    }
    if (data.settings) {
      setSettings((prev) => ({ ...prev, ...data.settings }));
    }
    setMessage("Settings saved successfully.");
  } catch (err) {
    setError(err.message || "Unable to save settings.");
  } finally {
    setSaving(false);
  }
}

function updateSetting(key, value) {
  setSettings((prev) => ({ ...prev, [key]: value }));
}

useEffect(() => {
  getStreamStatus();
  getSettings();
}, []);

useEffect(() => {
  const interval = setInterval(getStreamStatus, 5000);
  return () => clearInterval(interval);
}, []);

return (
  <div className="app">
    <AdminHeader isLive={isLive} />
    <AdminNavigation currentPage="settings" navigate={navigate} />

    <main className="dashboard">
      <section className="viewer-monitoring-page-header">
        <p className="eyebrow">ADMINISTRATION</p>
        <h1>Settings</h1>
        <p className="hero-text" style={{ marginTop: 10 }}>
          Configure stream defaults, viewer permissions, and platform options.
        </p>
      </section>

      {loading ? (
        <div className="screenshot-history-empty">
          <div className="screenshot-history-icon">⚙</div>
          <strong>Loading settings…</strong>
        </div>
      ) : (
        <form className="settings-form" onSubmit={saveSettings}>

          <section className="settings-section">
            <div className="section-title">
              <p className="eyebrow">VIEWER DEFAULTS</p>
              <h2>Permissions for new viewers</h2>
            </div>

            <div className="settings-grid">
              <label className="settings-toggle">
                <input
                  type="checkbox"
                  checked={!!settings.default_viewer_can_screenshot}
                  onChange={(e) =>
                    updateSetting("default_viewer_can_screenshot", e.target.checked)
                  }
                />
                <span>
                  <strong>Allow screenshots by default</strong>
                  <small>New viewers can capture screenshots without admin grant</small>
                </span>
              </label>

              <label className="settings-toggle">
                <input
                  type="checkbox"
                  checked={!!settings.default_viewer_can_record}
                  onChange={(e) =>
                    updateSetting("default_viewer_can_record", e.target.checked)
                  }
                />
                <span>
                  <strong>Allow recording by default</strong>
                  <small>New viewers can record the live stream without admin grant</small>
                </span>
              </label>

              <label className="settings-toggle">
                <input
                  type="checkbox"
                  checked={!!settings.require_viewer_permission}
                  onChange={(e) =>
                    updateSetting("require_viewer_permission", e.target.checked)
                  }
                />
                <span>
                  <strong>Require explicit permission</strong>
                  <small>Viewers need admin approval for capture actions when defaults are off</small>
                </span>
              </label>
            </div>
          </section>

          <section className="settings-section">
            <div className="section-title">
              <p className="eyebrow">STREAM</p>
              <h2>Broadcast options</h2>
            </div>

            <div className="settings-grid">
              <label className="settings-toggle">
                <input
                  type="checkbox"
                  checked={!!settings.auto_record_on_live}
                  onChange={(e) =>
                    updateSetting("auto_record_on_live", e.target.checked)
                  }
                />
                <span>
                  <strong>Auto-record when live</strong>
                  <small>Start an admin recording automatically when the stream goes live</small>
                </span>
              </label>

              <label className="settings-field">
                <span>Max concurrent viewers</span>
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={settings.max_viewer_sessions}
                  onChange={(e) =>
                    updateSetting(
                      "max_viewer_sessions",
                      Math.max(1, Number(e.target.value) || 1)
                    )
                  }
                />
              </label>

              <label className="settings-field">
                <span>Viewer session timeout (seconds)</span>
                <input
                  type="number"
                  min={5}
                  max={300}
                  value={settings.session_timeout_minutes}
                  onChange={(e) =>
                    updateSetting(
                      "session_timeout_minutes",
                      Math.max(5, Math.min(300, Number(e.target.value) || 20))
                    )
                  }
                />
                <small>
                  After the viewer closes the tab, mark them Timed out
                  if they stop polling within this many seconds.
                </small>
              </label>
            </div>
          </section>

          <section className="settings-section">
            <div className="section-title">
              <p className="eyebrow">VIDEO SOURCE</p>
              <h2>Input device</h2>
            </div>
            <div className="settings-grid">
              <label className="settings-toggle">
                <input
                  type="checkbox"
                  checked={!!settings.use_capture_card}
                  onChange={(e) =>
                    updateSetting("use_capture_card", e.target.checked)
                  }
                />
                <span>
                  <strong>Use capture card</strong>
                  <small>
                    Off = test video file. On = Windows capture device.
                    Stop and start the stream after changing.
                  </small>
                </span>
              </label>

              <label className="settings-field">
                <span>Capture device</span>
                <select
                  value={
                    [
                      "USB Video",
                      "USB Video Device",
                      "HD USB Camera",
                      "HDMI to USB",
                      "Capture Card",
                      "Game Capture",
                      "Elgato",
                      "AV TO USB2",
                      "Other",
                    ].includes(settings.capture_device_name)
                      ? settings.capture_device_name
                      : "Other"
                  }
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "Other") {
                      updateSetting("capture_device_name", "");
                    } else {
                      updateSetting("capture_device_name", v);
                    }
                  }}
                  disabled={!settings.use_capture_card}
                >
                  <option value="USB Video">USB Video</option>
                  <option value="USB Video Device">USB Video Device</option>
                  <option value="HD USB Camera">HD USB Camera</option>
                  <option value="HDMI to USB">HDMI to USB</option>
                  <option value="Capture Card">Capture Card</option>
                  <option value="Game Capture">Game Capture</option>
                  <option value="Elgato">Elgato</option>
                  <option value="AV TO USB2">AV TO USB2</option>
                  <option value="Other">Other (type exact name)</option>
                </select>
              </label>

              {(
                !settings.capture_device_name ||
                ![
                  "USB Video",
                  "USB Video Device",
                  "HD USB Camera",
                  "HDMI to USB",
                  "Capture Card",
                  "Game Capture",
                  "Elgato",
                  "AV TO USB2",
                ].includes(settings.capture_device_name)
              ) && settings.use_capture_card && (
                <label className="settings-field">
                  <span>Exact device name</span>
                  <input
                    type="text"
                    value={settings.capture_device_name || ""}
                    onChange={(e) =>
                      updateSetting("capture_device_name", e.target.value)
                    }
                    placeholder="Name from ffmpeg -list_devices"
                    disabled={!settings.use_capture_card}
                  />
                  <small>
                    ffmpeg -list_devices true -f dshow -i dummy
                  </small>
                </label>
              )}

              <label className="settings-field">
                <span>Stream quality (admin + viewers)</span>
                <select
                  value={settings.stream_quality || "720p"}
                  onChange={(e) =>
                    updateSetting("stream_quality", e.target.value)
                  }
                >
                  <option value="480p">480p</option>
                  <option value="720p">720p (default)</option>
                  <option value="1080p">1080p</option>
                </select>
                <small>
                  Applies on next stream Start (stop/start required).
                </small>
              </label>
            </div>
          </section>

          <section className="settings-section">
            <div className="section-title">
              <p className="eyebrow">ACCOUNT</p>
              <h2>Admin session</h2>
            </div>
            <div className="settings-info-card">
              <div>
                <span className="info-label">PLATFORM</span>
                <strong>DroneStream</strong>
              </div>
              <div>
                <span className="info-label">VERSION</span>
                <strong>v0.1.0</strong>
              </div>
              <div>
                <span className="info-label">STREAM STATUS</span>
                <strong>{stream?.status?.toUpperCase() || "OFFLINE"}</strong>
              </div>
            </div>
          </section>

          {(message || error) && (
            <div className={`message ${error ? "login-error" : ""}`}>
              {error || message}
            </div>
          )}

          <div className="settings-actions">
            <button
              type="submit"
              className="generate-link-button"
              disabled={saving}
            >
              {saving ? "SAVING…" : "SAVE SETTINGS"}
            </button>
          </div>
        </form>
      )}
    </main>

    <footer>
      <span>DRONESTREAM</span>
      <span>Secure streaming platform · v0.1.0</span>
    </footer>
  </div>
);
}

// ============================================================
// SECURITY LOGS PAGE
// ============================================================

function SecurityLogsPage({ navigate }) {

const [stream, setStream] = useState(null);
const [logs, setLogs] = useState([]);
const [loading, setLoading] = useState(false);
const [error, setError] = useState("");
const [filter, setFilter] = useState("all");

const isLive =
  String(stream?.status || "").toLowerCase() === "live";

async function getStreamStatus() {
  try {
    const response = await fetch(
      `${API_URL}/api/streams/status`,
      { credentials: "include" }
    );
    if (!response.ok) return;
    const data = await response.json();
    if (data.success) setStream(data.stream);
  } catch (err) {
    console.warn("DroneStream: security logs stream status error:", err);
  }
}

  async function clearSecurityLogs() {
    const isFiltered = filter && filter !== "all";
    const confirmMsg = isFiltered
      ? `Clear only logs matching filter "${filter}"?`
      : "Clear ALL security logs? One audit entry will remain for this action.";
    if (!window.confirm(confirmMsg)) {
      return;
    }
    try {
      const qs =
        isFiltered
          ? `?event=${encodeURIComponent(filter)}`
          : "";
      const response = await fetch(
        `${API_URL}/api/admin/security-logs${qs}`,
        {
          method: "DELETE",
          credentials: "include",
        }
      );
      const data = await response.json();
      if (!data.success) {
        setError(data.message || "Failed to clear logs.");
        return;
      }
      await getSecurityLogs();
    } catch {
      setError("Failed to clear security logs.");
    }
  }

async function getSecurityLogs() {
  setLoading(true);
  setError("");
  try {
    const response = await fetch(
      `${API_URL}/api/admin/security-logs`,
      { credentials: "include" }
    );
    if (!response.ok) {
      if (response.status === 404) {
        setLogs([]);
        return;
      }
      throw new Error("Unable to load security logs.");
    }
    const data = await response.json();
    if (data.success) {
      setLogs(data.logs || data.events || []);
    } else {
      setLogs([]);
    }
  } catch (err) {
    console.warn("DroneStream: security logs error:", err);
    setError(err.message || "Unable to load security logs.");
    setLogs([]);
  } finally {
    setLoading(false);
  }
}

useEffect(() => {
  getStreamStatus();
  getSecurityLogs();
}, []);

useEffect(() => {
  const interval = setInterval(() => {
    getStreamStatus();
    getSecurityLogs();
  }, 10000);
  return () => clearInterval(interval);
}, []);

const filteredLogs =
  filter === "all"
    ? logs
    : logs.filter((log) => {
        const event = String(
          log.event || log.action || log.type || ""
        ).toLowerCase();
        return event.includes(filter);
      });

return (
  <div className="app">
    <AdminHeader isLive={isLive} />
    <AdminNavigation currentPage="security" navigate={navigate} />

    <main className="dashboard">
      <section className="viewer-monitoring-page-header">
        <p className="eyebrow">ADMINISTRATION</p>
        <h1>Security Logs</h1>
        <p className="hero-text" style={{ marginTop: 10 }}>
          Audit logins, stream control, permission changes, and viewer activity.
        </p>
      </section>

      <div className="security-toolbar">
        <div className="security-filters">
          <label className="security-filter-label">
            <span>Filter by event</span>
            <select
              className="security-filter-select"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">All events</option>
              <option value="login">Login</option>
              <option value="logout">Logout</option>
              <option value="stream_start">Stream start</option>
              <option value="stream_stop">Stream stop</option>
              <option value="link_generate">Link generate</option>
              <option value="link_revoke">Link revoke</option>
              <option value="viewer_connect">Viewer connect</option>
              <option value="viewer_disconnect">Viewer disconnect</option>
              <option value="viewer_timeout">Viewer timeout</option>
              <option value="viewer_kick">Viewer kick</option>
              <option value="permission_grant">Permission grant</option>
              <option value="permission_revoke">Permission revoke</option>
              <option value="recording">Recording</option>
              <option value="screenshot">Screenshot</option>
              <option value="settings_updated">Settings updated</option>
              <option value="link_password_fail">Link password fail</option>
              <option value="recording_delete">Recording delete</option>
              <option value="recordings_cleared">Recordings cleared</option>
              <option value="screenshot_delete">Screenshot delete</option>
              <option value="screenshots_cleared">Screenshots cleared</option>
              <option value="security_logs_cleared">Security logs cleared</option>
              <option value="viewer_sessions_cleared">Viewer sessions cleared</option>
            </select>
          </label>
        </div>
        <button
          type="button"
          className="generate-link-button"
          onClick={getSecurityLogs}
          disabled={loading}
        >
          {loading ? "REFRESHING…" : "REFRESH"}
        </button>
        <button
          type="button"
          className="recording-action-button"
          onClick={clearSecurityLogs}
          disabled={loading}
          style={{ marginLeft: 8 }}
        >
          {filter && filter !== "all"
            ? `CLEAR FILTERED (${filter})`
            : "CLEAR ALL"}
        </button>
      </div>

      {error && (
        <div className="message login-error" style={{ marginBottom: 14 }}>
          {error}
        </div>
      )}

      {loading && logs.length === 0 ? (
        <div className="screenshot-history-empty">
          <div className="screenshot-history-icon">⌕</div>
          <strong>Loading security logs…</strong>
        </div>
      ) : filteredLogs.length === 0 ? (
        <div className="screenshot-history-empty">
          <div className="screenshot-history-icon">⌕</div>
          <strong>No security events</strong>
          <span>
            Events will appear here when admins log in, streams change state,
            or viewer permissions are updated.
          </span>
        </div>
      ) : (
        <div className="screenshot-history-table">
          <div className="screenshot-history-header security-log-header">
            <span>TIME</span>
            <span>EVENT</span>
            <span>ACTOR</span>
            <span>IP / SOURCE</span>
            <span>DETAIL</span>
          </div>

          {filteredLogs.map((log, index) => {
            const time =
              log.created_at ||
              log.timestamp ||
              log.time ||
              null;
            const event =
              log.event || log.action || log.type || "—";
            const actor =
              log.actor ||
              log.admin_username ||
              (log.admin_id ? `ADMIN #${log.admin_id}` : null) ||
              (log.viewer_session_id
                ? `VIEWER #${log.viewer_session_id}`
                : null) ||
              "—";
            const ip =
              log.ip_address || log.ip || log.source || "—";
            const detail =
              log.detail || log.message || log.description || "—";

            return (
              <div
                className="screenshot-history-row security-log-row"
                key={log.id || `${event}-${index}`}
              >
                <span title={time ? new Date(time).toLocaleString() : ""}>
                  {time
                    ? new Date(time).toLocaleString()
                    : "—"}
                </span>
                <span className="security-event-badge">{event}</span>
                <span>{actor}</span>
                <span>{ip}</span>
                <span title={detail}>{detail}</span>
              </div>
            );
          })}
        </div>
      )}
    </main>

    <footer>
      <span>DRONESTREAM</span>
      <span>Secure streaming platform · v0.1.0</span>
    </footer>
  </div>
);
}

// ============================================================
// VIEWER PAGE
// ============================================================

function ProjectorPage() {
  const [isLive, setIsLive] = useState(false);
  const [showChrome, setShowChrome] = useState(true);
  const rootRef = React.useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const response = await fetch(`${API_URL}/api/streams/status`, {
          credentials: "include",
        });
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled) return;
        const status = String(data?.stream?.status || "").toLowerCase();
        setIsLive(status === "live");
      } catch {
        // ignore
      }
    }

    poll();
    const interval = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!showChrome) return;
    const t = setTimeout(() => setShowChrome(false), 4000);
    return () => clearTimeout(t);
  }, [showChrome]);

  async function enterFullscreen() {
    const el = rootRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (el.requestFullscreen) {
        await el.requestFullscreen();
      } else if (el.webkitRequestFullscreen) {
        await el.webkitRequestFullscreen();
      }
    } catch (err) {
      console.warn("DroneStream: projector fullscreen:", err);
    }
  }

  return (
    <div
      ref={rootRef}
      onMouseMove={() => setShowChrome(true)}
      onClick={() => setShowChrome(true)}
      style={{
        margin: 0,
        padding: 0,
        width: "100vw",
        height: "100dvh",
        background: "#000",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        cursor: showChrome ? "default" : "none",
      }}
    >
      {showChrome && (
        <div
          style={{
            position: "absolute",
            top: 12,
            left: 16,
            right: 16,
            zIndex: 5,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              color: "#fff",
              fontSize: 12,
              fontWeight: 800,
              letterSpacing: "0.12em",
              opacity: 0.9,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: isLive ? "#e11d48" : "#6b7280",
                boxShadow: isLive ? "0 0 8px #e11d48" : "none",
              }}
            />
            {isLive ? "DRONESTREAM · LIVE" : "DRONESTREAM · OFFLINE"}
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              enterFullscreen();
            }}
            style={{
              pointerEvents: "auto",
              padding: "8px 14px",
              border: "1px solid #354052",
              borderRadius: 8,
              background: "rgba(15,18,24,0.85)",
              color: "#e7ebf1",
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: "0.08em",
              cursor: "pointer",
            }}
          >
            FULLSCREEN
          </button>
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0 }}>
        <AdminLivePreview isLive={isLive} />
      </div>
    </div>
  );
}

function ViewerPage({ token }) {

const videoRef =
React.useRef(null);

const [loading, setLoading] =
React.useState(true);

const [passwordRequired, setPasswordRequired] = useState(false);
const [viewerPassword, setViewerPassword] = useState("");
const [passwordSubmitting, setPasswordSubmitting] = useState(false);

const [error, setError] =
React.useState("");

const [streamInfo, setStreamInfo] =
React.useState(null);

const [connected, setConnected] =
React.useState(false);

const [viewerSessionId, setViewerSessionId] =
React.useState(null);

const [screenshotLoading, setScreenshotLoading] =
React.useState(false);

const [screenshotMessage, setScreenshotMessage] =
React.useState("");

const [recordingLoading, setRecordingLoading] =
React.useState(false);

const [recordingMessage, setRecordingMessage] =
React.useState("");

const [viewerIsRecording, setViewerIsRecording] =
React.useState(false);

const [viewerLastRecording, setViewerLastRecording] =
React.useState(null);

const [viewerLastScreenshot, setViewerLastScreenshot] = React.useState(null);

const mediaPanelRef = React.useRef(null);
const isViewingMedia = !!(viewerLastScreenshot || viewerLastRecording);

async function submitViewerPassword(e) {
  e.preventDefault();
  if (!viewerPassword.trim()) return;
  setPasswordSubmitting(true);
  setError("");
  try {
    sessionStorage.setItem(
      `dronestream_pwd_${token}`,
      viewerPassword.trim()
    );
  } catch {
    // ignore
  }
  setPasswordRequired(false);
  setPasswordSubmitting(false);
  window.location.reload();
}

React.useEffect(() => {
  if (isViewingMedia && mediaPanelRef.current) {
    mediaPanelRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}, [isViewingMedia, viewerLastScreenshot, viewerLastRecording]);

React.useEffect(() => {

let peerConnection = null;
let cancelled = false;

let viewerSessionId = null;


async function waitForIceGatheringComplete(pc) {

  if (
    pc.iceGatheringState ===
    "complete"
  ) {
    return;
  }

  await new Promise(
    (resolve) => {

      const checkState = () => {

        if (
          pc.iceGatheringState ===
          "complete"
        ) {

          pc.removeEventListener(
            "icegatheringstatechange",
            checkState
          );

          resolve();

        }

      };


      pc.addEventListener(
        "icegatheringstatechange",
        checkState
      );

    }
  );

}


async function disconnectViewerSession() {

  if (!viewerSessionId) {
    return;
  }

  try {

    await fetch(
      `${API_URL}/api/viewer/session/${encodeURIComponent(
        viewerSessionId
      )}/disconnect`,
      {
        method: "POST",
        keepalive: true,
      }
    );

    console.log(
      "DroneStream: viewer session disconnected."
    );

  } catch (error) {

    console.warn(
      "DroneStream: unable to disconnect viewer session:",
      error
    );

  }

}


async function connectToStream() {

  try {

    setLoading(true);
    setError("");
    setConnected(false);


    console.log(
      "DroneStream: viewer token:",
      token
    );


      // ----------------------------------------------------
    // 0. End previous session from THIS tab only (refresh)
    // ----------------------------------------------------

    try {
      const previousSessionId = sessionStorage.getItem(
        `dronestream_session_${token}`
      );
      if (previousSessionId) {
        await fetch(
          `${API_URL}/api/viewer/session/${encodeURIComponent(
            previousSessionId
          )}/disconnect`,
          {
            method: "POST",
            keepalive: true,
          }
        );
        sessionStorage.removeItem(`dronestream_session_${token}`);
      }
    } catch {
      // ignore
    }

    // ----------------------------------------------------
    // 1. Verify viewer access
    // ----------------------------------------------------

    const pwd =
      sessionStorage.getItem(`dronestream_pwd_${token}`) ||
      viewerPassword ||
      "";
    const accessUrl =
      `${API_URL}/api/viewer/stream/${encodeURIComponent(token)}` +
      (pwd ? `?password=${encodeURIComponent(pwd)}` : "");

    const accessResponse = await fetch(accessUrl);


    const accessData =
      await accessResponse.json();


    if (!accessResponse.ok) {

      throw new Error(
        accessData.message ||
        "Unable to verify viewer access."
      );

    }


    if (
      !accessData.success ||
      !accessData.authorized
    ) {
      if (accessData.password_required) {
        setPasswordRequired(true);
        setLoading(false);
        return;
      }
      throw new Error(
        accessData.message ||
        "Viewer access denied."
      );
    }

    setPasswordRequired(false);
    if (pwd) {
      try {
        sessionStorage.setItem(`dronestream_pwd_${token}`, pwd);
      } catch {
        // ignore
      }
    }


    if (cancelled) {
      return;
    }


    viewerSessionId =
      accessData.session_id;

    setViewerSessionId(
      accessData.session_id
    );

    try {
      sessionStorage.setItem(
        `dronestream_session_${token}`,
        accessData.session_id
      );
    } catch {
      // ignore
    }


    setStreamInfo(
      accessData.stream
    );


    // ----------------------------------------------------
    // 2. Create WebRTC connection
    // ----------------------------------------------------

    const iceConfigResponse = await fetch(`${API_URL}/api/webrtc/ice-config`);
    if (!iceConfigResponse.ok) {
      throw new Error("Unable to load WebRTC network configuration.");
    }
    const iceConfig = await iceConfigResponse.json();
    peerConnection = new RTCPeerConnection({
      iceServers: iceConfig.iceServers || [],
      iceTransportPolicy: "all",
    });


    // ----------------------------------------------------
    // 3. Receive video
    // ----------------------------------------------------

    peerConnection.addTransceiver(
      "video",
      {
        direction: "recvonly",
      }
    );


    peerConnection.ontrack =
      (event) => {

        console.log(
          "DroneStream: video track received."
        );


        if (cancelled) {
          return;
        }


        if (
          videoRef.current &&
          event.streams &&
          event.streams[0]
        ) {

          videoRef.current.srcObject =
            event.streams[0];


          videoRef.current
            .play()
            .catch(
              (err) => {

                console.warn(
                  "DroneStream: video autoplay warning:",
                  err
                );

              }
            );

        }


        setConnected(true);
        setLoading(false);

      };


    // ----------------------------------------------------
    // 4. WebRTC state monitoring
    // ----------------------------------------------------

    peerConnection.onconnectionstatechange =
      () => {

        if (!peerConnection) {
          return;
        }


        console.log(
          "DroneStream: connection state:",
          peerConnection.connectionState
        );


        if (
          peerConnection.connectionState ===
          "connected"
        ) {

          setConnected(true);
          setLoading(false);

        }


        if (
          peerConnection.connectionState ===
            "failed" ||
          peerConnection.connectionState ===
            "disconnected" ||
          peerConnection.connectionState ===
            "closed"
        ) {

          setConnected(false);

        }

      };


    peerConnection.oniceconnectionstatechange =
      () => {

        console.log(
          "DroneStream: ICE state:",
          peerConnection.iceConnectionState
        );

      };


    peerConnection.onicegatheringstatechange =
      () => {

        console.log(
          "DroneStream: ICE gathering:",
          peerConnection.iceGatheringState
        );

      };


    // ----------------------------------------------------
    // 5. Create browser offer
    // ----------------------------------------------------

    const offer =
      await peerConnection.createOffer();


    await peerConnection.setLocalDescription(
      offer
    );


    // ----------------------------------------------------
    // 6. Wait for ICE candidates
    // ----------------------------------------------------

    await waitForIceGatheringComplete(
      peerConnection
    );


    if (cancelled) {
      return;
    }


    // ----------------------------------------------------
    // 7. Send offer to FastAPI
    // ----------------------------------------------------

    const webrtcResponse =
      await fetch(
        `${API_URL}/api/webrtc/offer`,
        {
          method: "POST",

          headers: {
            "Content-Type":
              "application/json",
          },

          body: JSON.stringify({
            viewer_token: token,
            viewer_session_id: accessData.session_id,

            sdp:
              peerConnection
                .localDescription
                .sdp,

            type:
              peerConnection
                .localDescription
                .type,
          }),
        }
      );


    if (!webrtcResponse.ok) {

      let message =
        "WebRTC connection failed.";


      try {

        const data =
          await webrtcResponse.json();

        message =
          data.detail ||
          data.message ||
          message;

      } catch {
        // Keep default message.
      }


      throw new Error(message);

    }


    // ----------------------------------------------------
    // 8. Receive server answer
    // ----------------------------------------------------

    const answer =
      await webrtcResponse.json();


    // ----------------------------------------------------
    // 9. Set server answer
    // ----------------------------------------------------

    await peerConnection.setRemoteDescription(
      new RTCSessionDescription({
        type: answer.type,
        sdp: answer.sdp,
      })
    );


  } catch (err) {

    console.error(
      "DroneStream: connection error:",
      err
    );


    if (!cancelled) {

      setError(
        err.message ||
        "Unable to connect to the live stream."
      );

      setLoading(false);

    }

  }

}


connectToStream();

return () => {
  cancelled = true;
  disconnectViewerSession();
  if (peerConnection) {
    peerConnection.close();
  }
  if (videoRef.current) {
    videoRef.current.srcObject = null;
  }
};

}, [token]);

async function enterFullscreen() {
  const el = videoRef.current;
  if (!el) return;
  try {
    if (el.requestFullscreen) {
      await el.requestFullscreen();
    } else if (el.webkitRequestFullscreen) {
      await el.webkitRequestFullscreen();
    }
  } catch (err) {
    console.warn("DroneStream: fullscreen error:", err);
  }
}

async function enterPictureInPicture() {
  const el = videoRef.current;
  if (!el) return;
  try {
    if (document.pictureInPictureElement) {
      await document.exitPictureInPicture();
    } else if (el.requestPictureInPicture) {
      await el.requestPictureInPicture();
    }
  } catch (err) {
    console.warn("DroneStream: PiP error:", err);
  }
}

React.useEffect(() => {
  if (!viewerSessionId || error) {
    return;
  }

  let cancelled = false;

  async function checkSession() {
    try {
      const response = await fetch(
        `${API_URL}/api/viewer/session/${encodeURIComponent(
          viewerSessionId
        )}/status`
      );
      const data = await response.json();

      if (cancelled) return;

      if (!data.authorized) {
        setError(
          data.message ||
            "Your access to this stream has ended."
        );
        setConnected(false);
        if (videoRef.current) {
          videoRef.current.srcObject = null;
        }
      }
    } catch (err) {
      // network blip — ignore
    }
  }

  checkSession();
  const interval = setInterval(checkSession, 4000);

  return () => {
    cancelled = true;
    clearInterval(interval);
  };
}, [viewerSessionId, error]);

// ==========================================================
// VIEWER SCREENSHOT
// ==========================================================

async function captureScreenshot() {

  if (!viewerSessionId) {

    setScreenshotMessage(
      "Viewer session is not ready."
    );

    return;

  }


  try {

    setScreenshotLoading(true);

    setScreenshotMessage("");


    const response =
      await fetch(
        `${API_URL}/api/viewer/session/${encodeURIComponent(
          viewerSessionId
        )}/screenshot`,
        {
          method: "POST",
        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.message ||
        "Unable to capture screenshot."
      );

    }


    setScreenshotMessage(
      "Screenshot captured successfully."
    );

    setViewerLastScreenshot(
      data.screenshot
    );


    console.log(
      "DroneStream: screenshot captured:",
      data.screenshot
    );


  } catch (error) {

    console.error(
      "DroneStream: screenshot error:",
      error
    );


    setScreenshotMessage(
      error.message ||
      "Unable to capture screenshot."
    );


  } finally {

    setScreenshotLoading(false);

  }

}

// ==========================================================
// VIEWER RECORDING
// ==========================================================

async function startViewerRecording() {

  if (!viewerSessionId) {

    setRecordingMessage(
      "Viewer session is not ready."
    );

    return;

  }


  try {

    setRecordingLoading(true);

    setRecordingMessage("");


    const response =
      await fetch(
        `${API_URL}/api/viewer/session/${encodeURIComponent(
          viewerSessionId
        )}/recording/start`,
        {
          method: "POST",
        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.message ||
        "Unable to start recording."
      );

    }


    setViewerIsRecording(true);

    setRecordingMessage(
      "Recording started."
    );


    console.log(
      "DroneStream: viewer recording started:",
      data.recording
    );


  } catch (error) {

    console.error(
      "DroneStream: viewer recording start error:",
      error
    );


    setRecordingMessage(
      error.message ||
      "Unable to start recording."
    );


  } finally {

    setRecordingLoading(false);

  }

}


async function stopViewerRecording() {

  if (!viewerSessionId) {

    setRecordingMessage(
      "Viewer session is not ready."
    );

    return;

  }


  try {

    setRecordingLoading(true);

    setRecordingMessage("");


    const response =
      await fetch(
        `${API_URL}/api/viewer/session/${encodeURIComponent(
          viewerSessionId
        )}/recording/stop`,
        {
          method: "POST",
        }
      );


    const data =
      await response.json();


    if (
      !response.ok ||
      !data.success
    ) {

      throw new Error(
        data.message ||
        "Unable to stop recording."
      );

    }


    setViewerIsRecording(false);

    setRecordingMessage(
      "Recording stopped and saved."
    );

    setViewerLastRecording(
      data.recording
    );


    console.log(
      "DroneStream: viewer recording stopped:",
      data.recording
    );


  } catch (error) {

    console.error(
      "DroneStream: viewer recording stop error:",
      error
    );


    setRecordingMessage(
      error.message ||
      "Unable to stop recording."
    );


  } finally {

    setRecordingLoading(false);

  }

}

// ==========================================================
// ERROR SCREEN
// ==========================================================

if (error) {

return (

  <div className="viewer-page">

    <header className="viewer-header">

      <div className="brand">
        DRONESTREAM
      </div>

      <div className="viewer-status offline">
        ACCESS DENIED
      </div>

    </header>


    <main className="viewer-content">

      <section className="viewer-error">

        <div className="error-icon">
          🔒
        </div>

        <h1>
          Stream Access Denied
        </h1>

        <p>
          {error}
        </p>

      </section>

    </main>

  </div>

);

}

if (passwordRequired) {
  return (
    <div className="viewer-page">
      <header className="viewer-header">
        <div className="brand">DRONESTREAM</div>
        <div className="viewer-status offline">PASSWORD REQUIRED</div>
      </header>
      <main className="viewer-content">
        <section className="viewer-error">
          <div className="error-icon">🔒</div>
          <h1>Enter access password</h1>
          <p>This stream link is password protected.</p>
          <form onSubmit={submitViewerPassword} style={{ marginTop: 16 }}>
            <input
              type="password"
              value={viewerPassword}
              onChange={(e) => setViewerPassword(e.target.value)}
              placeholder="Password"
              autoFocus
              style={{
                width: "100%",
                maxWidth: 280,
                padding: "12px 14px",
                border: "1px solid #303846",
                borderRadius: 8,
                background: "#0b0f16",
                color: "#e7ebf1",
                fontSize: 14,
              }}
            />
            <div style={{ marginTop: 12 }}>
              <button
                type="submit"
                disabled={passwordSubmitting || !viewerPassword.trim()}
                style={{
                  padding: "12px 20px",
                  border: "1px solid #354052",
                  borderRadius: 8,
                  background: "#151a23",
                  color: "#e7ebf1",
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                {passwordSubmitting ? "CHECKING..." : "UNLOCK"}
              </button>
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}

// ==========================================================
// VIEWER
// ==========================================================

return (

<div className={`viewer-page${isViewingMedia ? " viewing-media" : ""}`}>

  <header className="viewer-header">

    <div className="brand">
      DRONESTREAM
    </div>


    <div
      className={`viewer-status ${
        connected
          ? "live"
          : "offline"
      }`}
    >

      <span className="status-dot"></span>

      {connected
        ? "LIVE"
        : "CONNECTING"}

    </div>

  </header>


  <main className="viewer-content">

    {isViewingMedia && (

      <section
        className="viewer-media-panel"
        ref={mediaPanelRef}
      >

        {viewerLastScreenshot && (

          <div className="recording-player">

            <div className="recording-player-header">

              <span>
                {viewerLastScreenshot.file_name}
              </span>

              <div className="recording-actions">

                <a
                  className="recording-action-button"
                  href={`${API_URL}/api/viewer/session/${encodeURIComponent(
                    viewerSessionId
                  )}/screenshots/${viewerLastScreenshot.id}/download`}
                >
                  DOWNLOAD
                </a>

                <button
                  type="button"
                  className="recording-action-button"
                  onClick={() => setViewerLastScreenshot(null)}
                >
                  CLOSE
                </button>

              </div>

            </div>

            <img
              src={`${API_URL}/api/viewer/session/${encodeURIComponent(
                viewerSessionId
              )}/screenshots/${viewerLastScreenshot.id}/view`}
              alt={viewerLastScreenshot.file_name}
            />

          </div>

        )}

        {viewerLastRecording && (

          <div className="recording-player">

            <div className="recording-player-header">

              <span>
                {viewerLastRecording.file_name}
              </span>

              <div className="recording-actions">

                <a
                  className="recording-action-button"
                  href={`${API_URL}/api/viewer/session/${encodeURIComponent(
                    viewerSessionId
                  )}/recordings/${viewerLastRecording.id}/download`}
                >
                  DOWNLOAD
                </a>

                <button
                  type="button"
                  className="recording-action-button"
                  onClick={() => setViewerLastRecording(null)}
                >
                  CLOSE
                </button>

              </div>

            </div>

            <video
              controls
              autoPlay
              src={`${API_URL}/api/viewer/session/${encodeURIComponent(
                viewerSessionId
              )}/recordings/${viewerLastRecording.id}/stream`}
            />

          </div>

        )}

      </section>

    )}

    <section
      className="video-container"
      style={isViewingMedia ? { display: "none" } : undefined}
    >

      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        controls={false}
      />


      {loading && (

        <div className="video-overlay">

          <div className="loading-spinner"></div>

          <div>
            Connecting to live stream...
          </div>

        </div>

      )}

    </section>


    {!isViewingMedia && (

      <>

        <section className="viewer-controls">

          <button
            type="button"
            className="viewer-screenshot-button"
            onClick={captureScreenshot}
            disabled={
              !viewerSessionId ||
              !connected ||
              screenshotLoading
            }
          >
            {screenshotLoading
              ? "CAPTURING..."
              : "📸 SCREENSHOT"}
          </button>

          <button
            type="button"
            className="viewer-recording-button"
            onClick={
              viewerIsRecording
                ? stopViewerRecording
                : startViewerRecording
            }
            disabled={
              !viewerSessionId ||
              !connected ||
              recordingLoading
            }
          >
            {recordingLoading
              ? (viewerIsRecording
                  ? "STOPPING..."
                  : "STARTING...")
              : (viewerIsRecording
                  ? "⏹ STOP RECORDING"
                  : "🔴 RECORD")}
          </button>

          <button
            type="button"
            className="viewer-screenshot-button"
            onClick={enterFullscreen}
            disabled={!connected}
          >
            ⛶ FULLSCREEN
          </button>

          <button
            type="button"
            className="viewer-screenshot-button"
            onClick={enterPictureInPicture}
            disabled={!connected}
          >
            ⧉ PiP
          </button>

        </section>

        {(screenshotMessage || recordingMessage) && (

          <div className="viewer-messages">

            {screenshotMessage && (

              <div className="screenshot-message">
                {screenshotMessage}
              </div>

            )}

            {recordingMessage && (

              <div className="recording-message">
                {recordingMessage}
              </div>

            )}

          </div>

        )}


        <section className="viewer-info">

          <div>

            <span className="info-label">
              STREAM
            </span>

            <span className="info-value">
              {streamInfo?.id || "—"}
            </span>

          </div>


          <div>

            <span className="info-label">
              VIEWERS
            </span>

            <span className="info-value">
              {streamInfo?.viewer_count ?? 0}
            </span>

          </div>


          <div>

            <span className="info-label">
              CONNECTION
            </span>

            <span className="info-value">
              {loading
                ? "Connecting…"
                : connected
                  ? "🔒 Live · WebRTC"
                  : "Reconnecting…"}
            </span>

          </div>

        </section>


        <div className="viewer-security">

          <span>
            🔒
          </span>

          Authorized DroneStream connection

        </div>

      </>

    )}

  </main>

</div>

);

}

// ============================================================
// APP ROUTING
// ============================================================

function App() {

const [path, setPath] =
useState(window.location.pathname);

// ----------------------------------------------------------
// Browser navigation support
// ----------------------------------------------------------

useEffect(() => {

const handlePopState = () => {

  setPath(
    window.location.pathname
  );

};


window.addEventListener(
  "popstate",
  handlePopState
);


return () => {

  window.removeEventListener(
    "popstate",
    handlePopState
  );

};

}, []);

// ----------------------------------------------------------
// Internal navigation
// ----------------------------------------------------------

function navigate(newPath) {

if (
  window.location.pathname ===
  newPath
) {
  return;
}


window.history.pushState(
  {},
  "",
  newPath
);


setPath(newPath);

window.scrollTo({
  top: 0,
  behavior: "smooth",
});

}

// ----------------------------------------------------------
// Viewer route
// ----------------------------------------------------------

if (path === "/broadcast") {
  return <BroadcasterPage />;
}

if (
path.startsWith("/watch/")
) {

const token =
  decodeURIComponent(
    path.substring(
      "/watch/".length
    )
  );


return (
  <ViewerPage
    token={token}
  />
);

}

// ----------------------------------------------------------

// Viewer monitoring route
// ----------------------------------------------------------

if (
path === "/admin/viewers"
) {

return (
  <AuthGate>
    <ViewerMonitoringPage
      navigate={navigate}
    />
  </AuthGate>
);

}

// ----------------------------------------------------------
// Recordings route
// ----------------------------------------------------------

if (
  path === "/admin/recordings"
) {

  return (
    <AuthGate>
      <RecordingsPage
        navigate={navigate}
      />
    </AuthGate>
  );

}

// ----------------------------------------------------------
// Screenshots route
// ----------------------------------------------------------

if (
  path === "/admin/screenshots"
) {

  return (
    <AuthGate>
      <ScreenshotsPage
        navigate={navigate}
      />
    </AuthGate>
  );

}

if (path === "/admin/settings") {
  return (
    <AuthGate>
      <SettingsPage navigate={navigate} />
    </AuthGate>
  );
}

if (path === "/admin/broadcasters") {
  return (
    <AuthGate>
      <BroadcastersAdminPage navigate={navigate} />
    </AuthGate>
  );
}

if (path === "/admin/security") {
  return (
    <AuthGate>
      <SecurityLogsPage navigate={navigate} />
    </AuthGate>
  );
}

if (path === "/admin/projector") {
  return (
    <AuthGate>
      <ProjectorPage />
    </AuthGate>
  );
}

// ----------------------------------------------------------
// Default admin dashboard
// ----------------------------------------------------------

return (
  <AuthGate>
    <AdminPage
      navigate={navigate}
    />
  </AuthGate>
);

}

export default App;