"use client";
import { useEffect, useRef } from "react";
import { Box } from "@chakra-ui/react";
import { useCallStateHooks } from "@stream-io/video-react-sdk";

export default function CameraView() {
  const { useCameraState } = useCallStateHooks();
  const { mediaStream } = useCameraState();
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current && mediaStream) {
      videoRef.current.srcObject = mediaStream;
    }
  }, [mediaStream]);

  return (
    <Box
      as="video"
      ref={videoRef}
      autoPlay
      playsInline
      muted
      w="full"
      h="full"
      objectFit="cover"
      position="absolute"
      top={0}
      left={0}
    />
  );
}
