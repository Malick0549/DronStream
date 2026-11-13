// WebSocket video relay (browser side).
//
// Broadcaster: records the capture in short, self-contained WebM
// segments and sends each one to the server over a WebSocket.
// Viewer: receives those segments and plays them with Media Source.
//
// WebSockets travel through the Cloudflare tunnel like normal pages,
// so no TURN server or open ports are needed.

const SEGMENT_MS = 2000;
const MAX_QUEUED_SEGMENTS = 6;
const MAX_UNSENT_BYTES = 4 * 1024 * 1024;
const MIME_CANDIDATES = [
  "video/webm;codecs=vp8",
  "video/webm;codecs=vp9",
  "video/webm",
];

function wsBase() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

// ------------------------------------------------------------
// BROADCASTER
// ------------------------------------------------------------

export function startRelayPublish(capture, streamId, onStatus = () => {}) {
  const mime = MIME_CANDIDATES.find(
    (type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)
  );
  if (!mime) {
    onStatus("This browser cannot record video for the relay.");
    return () => {};
  }

  const ws = new WebSocket(
    `${wsBase()}/api/relay/publish/${encodeURIComponent(streamId)}`
  );
  let timer = null;
  let current = null;
  let stopped = false;

  function startRecorder() {
    const chunks = [];
    const recorder = new MediaRecorder(capture, {
      mimeType: mime,
      videoBitsPerSecond: 1500000,
    });
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size) chunks.push(event.data);
    };
    recorder.onstop = async () => {
      if (!chunks.length || ws.readyState !== WebSocket.OPEN) return;
      // If the connection is too slow, skip this segment instead of
      // building up delay.
      if (ws.bufferedAmount > MAX_UNSENT_BYTES) return;
      const data = await new Blob(chunks, { type: mime }).arrayBuffer();
      if (ws.readyState === WebSocket.OPEN) ws.send(data);
    };
    recorder.start();
    return recorder;
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    clearInterval(timer);
    try {
      if (current && current.state !== "inactive") current.stop();
    } catch {
      // ignore
    }
    try {
      ws.close();
    } catch {
      // ignore
    }
  }

  ws.onopen = () => {
    ws.send(mime);
    current = startRecorder();
    // Start the next recorder before stopping the old one so no
    // video is lost between segments.
    timer = setInterval(() => {
      const previous = current;
      current = startRecorder();
      if (previous.state !== "inactive") previous.stop();
    }, SEGMENT_MS);
    onStatus("Relay connected.");
  };
  ws.onclose = (event) => {
    clearInterval(timer);
    if (!stopped) onStatus(`Relay closed (code ${event.code}).`);
  };
  ws.onerror = () => onStatus("Relay connection error.");

  return stop;
}

// ------------------------------------------------------------
// VIEWER
// ------------------------------------------------------------

export function startRelayWatch(video, token, sessionId, onEvent = () => {}) {
  const ws = new WebSocket(
    `${wsBase()}/api/relay/watch?token=${encodeURIComponent(token)}` +
      `&session_id=${encodeURIComponent(sessionId)}`
  );
  ws.binaryType = "arraybuffer";

  let mediaSource = null;
  let sourceBuffer = null;
  let objectUrl = null;
  let playing = false;
  const queue = [];

  function pump() {
    if (!sourceBuffer || sourceBuffer.updating || !queue.length) return;
    try {
      sourceBuffer.appendBuffer(queue.shift());
    } catch (error) {
      console.warn("DroneStream relay: append failed:", error);
    }
  }

  function onUpdateEnd() {
    const ranges = video.buffered;
    if (ranges.length) {
      const start = ranges.start(0);
      const end = ranges.end(ranges.length - 1);
      // Stay close to live: if we fell behind, jump forward.
      if (end - video.currentTime > 4) video.currentTime = end - 1;
      // Free memory: drop video that was played a while ago.
      if (!sourceBuffer.updating && video.currentTime - start > 15) {
        try {
          sourceBuffer.remove(0, video.currentTime - 10);
        } catch {
          // ignore
        }
      }
    }
    if (!playing && video.readyState >= 2) {
      playing = true;
      onEvent("playing");
    }
    if (video.paused) video.play().catch(() => {});
    pump();
  }

  function setup(mime) {
    if (mediaSource) return;
    if (!window.MediaSource || !MediaSource.isTypeSupported(mime)) {
      onEvent("unsupported");
      ws.close();
      return;
    }
    mediaSource = new MediaSource();
    objectUrl = URL.createObjectURL(mediaSource);
    video.src = objectUrl;
    mediaSource.addEventListener(
      "sourceopen",
      () => {
        sourceBuffer = mediaSource.addSourceBuffer(mime);
        sourceBuffer.mode = "sequence";
        sourceBuffer.addEventListener("updateend", onUpdateEnd);
        pump();
      },
      { once: true }
    );
  }

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
      setup(event.data);
      return;
    }
    queue.push(event.data);
    while (queue.length > MAX_QUEUED_SEGMENTS) queue.shift();
    pump();
  };
  ws.onclose = (event) => onEvent("closed", event.code);
  ws.onerror = () => onEvent("error");

  return function stop() {
    try {
      ws.close();
    } catch {
      // ignore
    }
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    video.removeAttribute("src");
    video.load();
  };
}