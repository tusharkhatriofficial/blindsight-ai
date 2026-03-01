"use client";
import { useState, useCallback } from "react";
import {
  StreamVideo,
  StreamVideoClient,
  StreamCall,
} from "@stream-io/video-react-sdk";
import "@stream-io/video-react-sdk/dist/css/styles.css";
import LandingScreen from "@/components/LandingScreen";
import ActiveCallScreen from "@/components/ActiveCallScreen";
import AgentAudioPlayer from "@/components/AgentAudioPlayer";

const CALL_ID = "blindsight-live";

export default function HomePage() {
  const [client, setClient] = useState<StreamVideoClient | null>(null);
  const [call, setCall] = useState<ReturnType<StreamVideoClient["call"]> | null>(null);
  const [connected, setConnected] = useState(false);

  const handleStart = useCallback(async () => {
    // ── iOS audio unlock ─────────────────────────────────────────────────────
    // MUST be synchronous before the first `await` — only works inside a
    // direct user-gesture handler. Resumes the Web AudioContext so that
    // audio elements created later (by Stream SDK) are allowed to play.
    try {
      const AC =
        (window as any).AudioContext ||
        (window as any).webkitAudioContext;
      if (AC) {
        const ctx = new AC() as AudioContext;
        ctx.resume();
        const buf = ctx.createBuffer(1, 1, 22050);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.connect(ctx.destination);
        src.start(0);
      }
    } catch (_) { /* non-fatal */ }
    // ─────────────────────────────────────────────────────────────────────────

    const userId = "user-" + Math.random().toString(36).slice(2, 8);

    const res = await fetch(`/api/token?userId=${userId}`);
    const { token } = await res.json();

    const videoClient = new StreamVideoClient({
      apiKey: process.env.NEXT_PUBLIC_STREAM_API_KEY!,
      user: { id: userId, name: "BlindSight User" },
      token,
    });

    const videoCall = videoClient.call("default", CALL_ID);
    await videoCall.join({ create: true });

    // Enable mic first — works over HTTP
    try {
      await videoCall.microphone.enable();
    } catch (e) {
      console.warn("Microphone enable failed:", e);
    }

    // Camera requires a secure context (HTTPS) on iOS Safari
    // Attempt rear-facing; surface a readable error if blocked
    try {
      await videoCall.camera.selectDirection("back");
      await videoCall.camera.enable();
    } catch (e: any) {
      const msg: string = e?.message ?? String(e);
      // Re-throw with a clear message so LandingScreen can display it
      if (
        msg.toLowerCase().includes("permission") ||
        msg.toLowerCase().includes("notallowed") ||
        msg.toLowerCase().includes("https") ||
        msg.toLowerCase().includes("secure") ||
        msg.toLowerCase().includes("not supported")
      ) {
        await videoCall.leave();
        await videoClient.disconnectUser();
        throw new Error(
          "Camera permission denied. On iPhone Safari, HTTPS is required. Open the app via your Vercel URL instead."
        );
      }
      // Non-fatal: join without camera
      console.warn("Camera enable failed (non-fatal):", e);
    }

    setClient(videoClient);
    setCall(videoCall);
    setConnected(true);

    // Trigger Stream SDK's internal AudioContext click-resume listener.
    // The SDK adds document.addEventListener('click', resumeAudioContext)
    // when it creates its AudioContext — dispatching a synthetic click fires it.
    setTimeout(() => {
      document.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    }, 500);
  }, []);

  const handleStop = useCallback(async () => {
    // Unmount the call UI first so SDK hooks don't fire during teardown
    setConnected(false);
    // Small tick to let React unmount CameraView / ActiveCallScreen
    await new Promise((r) => setTimeout(r, 50));
    await call?.leave();
    await client?.disconnectUser();
    setClient(null);
    setCall(null);
  }, [call, client]);

  if (!connected || !client || !call) {
    return <LandingScreen onStart={handleStart} />;
  }

  return (
    <StreamVideo client={client}>
      <StreamCall call={call}>
        {/* Routes agent audio through speaker instead of iOS earpiece */}
        <AgentAudioPlayer />
        <ActiveCallScreen onStop={handleStop} call={call} />
      </StreamCall>
    </StreamVideo>
  );
}
