"use client";
/**
 * AgentAudioPlayer — forces the agent's audio through the speaker on iOS.
 *
 * Problem: when WebRTC captures mic + camera on iOS Safari, iOS enters
 * "phone call mode" and routes ALL audio output to the earpiece, not the
 * external speaker. The user hears nothing unless they hold the phone to
 * their ear.
 *
 * Fix: attach the remote participant's audioStream to a hidden <video>
 * element with playsInline. iOS routes <video> audio through the speaker,
 * and this overrides the earpiece routing set by getUserMedia audio capture.
 */
import { useEffect, useRef } from "react";
import { useCallStateHooks } from "@stream-io/video-react-sdk";

export default function AgentAudioPlayer() {
  const { useRemoteParticipants } = useCallStateHooks();
  const remoteParticipants = useRemoteParticipants();
  const videoRef = useRef<HTMLVideoElement>(null);

  // Use the first remote participant that has an audioStream (the AI agent)
  const audioStream =
    remoteParticipants.find((p) => p.audioStream)?.audioStream ?? null;

  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    if (el.srcObject === audioStream) return;

    // React has a known bug where muted={false} is ignored; set via DOM ref
    el.muted = false;
    el.srcObject = audioStream;

    if (audioStream) {
      el.play().catch((err) => {
        console.warn("[AgentAudioPlayer] play() blocked:", err);
      });
    }
  }, [audioStream]);

  return (
    <video
      ref={videoRef}
      autoPlay
      playsInline
      // keep out of layout — zero dimensions, no render cost
      style={{ position: "fixed", width: 0, height: 0, opacity: 0 }}
    />
  );
}
