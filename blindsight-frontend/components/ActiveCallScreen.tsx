"use client";
import {
  Box,
  HStack,
  Text,
  Circle,
} from "@chakra-ui/react";
import { useState } from "react";
import CameraView from "./CameraView";

interface Props {
  onStop: () => Promise<void>;
  call: any;
}

export default function ActiveCallScreen({ onStop, call }: Props) {
  const [facingBack, setFacingBack] = useState(true);
  const [stopping, setStopping] = useState(false);

  const flipCamera = async () => {
    try {
      await call.camera.flip();
      setFacingBack((prev) => !prev);
    } catch {
      // Ignore device switch errors on devices with single camera
    }
  };

  const handleStop = async () => {
    if (stopping) return;
    setStopping(true);
    await onStop();
  };

  return (
    <Box position="fixed" inset={0} bg="black" overflow="hidden">
      {/* Full screen camera feed */}
      <Box position="absolute" inset={0}>
        <CameraView />
      </Box>

      {/* Status pill — top left */}
      <Box
        position="absolute"
        top="env(safe-area-inset-top, 16px)"
        left={4}
        zIndex={10}
      >
        <HStack
          spacing={2}
          bg="blackAlpha.700"
          px={3}
          py={2}
          borderRadius="full"
          backdropFilter="blur(8px)"
        >
          <Circle
            size="8px"
            bg="green.400"
            sx={{
              "@keyframes pulse": {
                "0%, 100%": { opacity: 1 },
                "50%": { opacity: 0.4 },
              },
              animation: "pulse 2s infinite",
            }}
          />
          <Text fontSize="xs" color="green.300" fontWeight="500">
            AI Watching
          </Text>
        </HStack>
      </Box>

      {/* Bottom controls */}
      <Box
        position="absolute"
        bottom={0}
        left={0}
        right={0}
        pb="env(safe-area-inset-bottom, 24px)"
        pt={4}
        px={8}
        background="linear-gradient(to top, rgba(0,0,0,0.9), transparent)"
        zIndex={10}
      >
        <HStack justify="space-between" align="center">
          {/* Flip camera */}
          <Circle
            size="56px"
            bg="whiteAlpha.200"
            cursor="pointer"
            onClick={flipCamera}
            _active={{ transform: "scale(0.9)" }}
            as="button"
          >
            <Text fontSize="xl" userSelect="none">
              &#8635;
            </Text>
          </Circle>

          {/* Stop / End session */}
          <Circle
            size="72px"
            bg="red.500"
            cursor="pointer"
            onClick={handleStop}
            _active={{ transform: "scale(0.9)" }}
            as="button"
            opacity={stopping ? 0.5 : 1}
            aria-label="End session"
          >
            <Box w="22px" h="22px" bg="white" borderRadius="4px" />
          </Circle>

          {/* Mic active indicator */}
          <Circle size="56px" bg="whiteAlpha.200">
            <Text fontSize="xl" color="white" userSelect="none">
              &#9679;
            </Text>
          </Circle>
        </HStack>

        <Text
          fontSize="xs"
          color="whiteAlpha.500"
          textAlign="center"
          mt={3}
        >
          Speak naturally to ask questions
        </Text>
      </Box>
    </Box>
  );
}
