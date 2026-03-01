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

const CALL_ID = "blindsight-live";

export default function HomePage() {
  const [client, setClient] = useState<StreamVideoClient | null>(null);
  const [call, setCall] = useState<ReturnType<StreamVideoClient["call"]> | null>(null);

  const handleStart = useCallback(async () => {
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
  }, []);

  const handleStop = useCallback(async () => {
    await call?.leave();
    await client?.disconnectUser();
    setClient(null);
    setCall(null);
  }, [call, client]);

  if (!client || !call) {
    return <LandingScreen onStart={handleStart} />;
  }

  return (
    <StreamVideo client={client}>
      <StreamCall call={call}>
        <ActiveCallScreen onStop={handleStop} call={call} />
      </StreamCall>
    </StreamVideo>
  );
}
