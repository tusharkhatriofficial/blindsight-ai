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

    // Use rear-facing camera for navigation
    await videoCall.camera.selectDirection("back");
    await videoCall.camera.enable();
    await videoCall.microphone.enable();

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
