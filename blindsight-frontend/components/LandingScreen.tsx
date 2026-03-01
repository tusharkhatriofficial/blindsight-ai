"use client";
import {
  Box,
  Button,
  Text,
  VStack,
  Heading,
  Center,
  Alert,
  AlertIcon,
  AlertDescription,
} from "@chakra-ui/react";
import { useState } from "react";

interface Props {
  onStart: () => Promise<void>;
}

export default function LandingScreen({ onStart }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleTap = async () => {
    setLoading(true);
    setError(null);
    try {
      await onStart();
    } catch (err: any) {
      const msg = err?.message ?? String(err);
      if (msg.toLowerCase().includes("https") || msg.toLowerCase().includes("secure") || msg.toLowerCase().includes("notallowed") || msg.toLowerCase().includes("permission")) {
        setError("Camera blocked: this page needs HTTPS. Open it via your Vercel URL or use the Chrome browser on Android.");
      } else {
        setError(msg || "Something went wrong. Check your API keys and try again.");
      }
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

        {error && (
          <Alert status="error" borderRadius="xl" bg="red.900" color="white">
            <AlertIcon color="red.300" />
            <AlertDescription fontSize="sm">{error}</AlertDescription>
          </Alert>
        )}

        <Text fontSize="xs" color="gray.600" textAlign="center">
          Allow camera and microphone access when prompted
        </Text>
      </VStack>
    </Center>
  );
}
