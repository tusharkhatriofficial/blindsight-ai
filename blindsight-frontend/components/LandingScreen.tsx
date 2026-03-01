"use client";
import {
  Box,
  Button,
  Text,
  VStack,
  Heading,
  Center,
} from "@chakra-ui/react";
import { useState } from "react";

interface Props {
  onStart: () => Promise<void>;
}

export default function LandingScreen({ onStart }: Props) {
  const [loading, setLoading] = useState(false);

  const handleTap = async () => {
    setLoading(true);
    try {
      await onStart();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Center minH="100dvh" px={6} bg="black">
      <VStack spacing={10} w="full" maxW="400px">
        <VStack spacing={3} textAlign="center">
          <Heading
            fontSize="3xl"
            fontWeight="700"
            color="white"
            letterSpacing="-0.5px"
          >
            BlindSight AI
          </Heading>
          <Text fontSize="md" color="gray.400" lineHeight="tall">
            Real-time visual guide powered by AI. Point your camera and let
            the AI be your eyes.
          </Text>
        </VStack>

        <Button
          w="full"
          h="64px"
          borderRadius="2xl"
          bg="white"
          color="black"
          fontSize="lg"
          fontWeight="600"
          onClick={handleTap}
          isLoading={loading}
          loadingText="Connecting..."
          _active={{ transform: "scale(0.97)" }}
          _hover={{ bg: "gray.100" }}
        >
          Start Session
        </Button>

        <Text fontSize="xs" color="gray.600" textAlign="center">
          Allow camera and microphone access when prompted
        </Text>
      </VStack>
    </Center>
  );
}
