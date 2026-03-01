import asyncio
import argparse
import base64
import io
import logging
import os
import sys
import time
from typing import Optional

import aiortc
import av
import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from openai import AsyncOpenAI

load_dotenv()

# ── Startup env validation ────────────────────────────────────────────────────
_REQUIRED_ENV = ["OPENAI_API_KEY", "STREAM_API_KEY", "STREAM_API_SECRET"]
_missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
if _missing:
    print(
        f"\n[BlindSight AI] Missing required environment variables: {', '.join(_missing)}\n"
        "Copy .env.example to .env and fill in your API keys.\n",
        file=sys.stderr,
    )
    sys.exit(1)

from vision_agents.core import User, Agent, AgentLauncher, Runner
from vision_agents.core.processors import VideoProcessorPublisher
from vision_agents.core.utils.video_track import QueuedVideoTrack
from vision_agents.core.utils.video_forwarder import VideoForwarder
from vision_agents.plugins import openai, getstream, smart_turn

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ObstacleAnnotationProcessor
# Captures frames at 1fps, sends to gpt-4o-mini for accurate scene analysis,
# stamps the analysis as a text overlay on each frame, and publishes the
# annotated frame. gpt-4o-realtime sees the text overlay as ground truth.
# ─────────────────────────────────────────────────────────────────────────────

VISION_PROMPT = (
    "You are helping a blind person navigate safely. Look at this camera frame carefully.\n"
    "1. Is the forward path BLOCKED or CLEAR?\n"
    "   BLOCKED = a solid large object (wardrobe, wall, door, cabinet, furniture, person, car) "
    "occupies the centre of the frame and would physically stop forward movement.\n"
    "   CLEAR = open floor or open space extends several metres straight ahead. A road, "
    "hallway, pavement, or empty room = CLEAR.\n"
    "2. What specifically is the obstacle (if any)?\n"
    "Reply in this EXACT format — one line only:\n"
    "STATUS: BLOCKED | Wardrobe fills entire view\n"
    "STATUS: CLEAR | Open hallway ahead\n"
    "STATUS: BLOCKED | Closed door directly in front\n"
    "STATUS: CLEAR | Road stretching forward\n"
    "Be precise. Use what you actually see, not guesses."
)


class ObstacleAnnotationProcessor(VideoProcessorPublisher):
    """
    Per-frame accurate obstacle detection using gpt-4o-mini vision.
    Annotates each video frame with the detection result so gpt-4o-realtime
    reads ground-truth scene data instead of guessing from raw pixels.
    """

    name = "obstacle_annotator"

    def __init__(self, analysis_fps: int = 1, output_fps: int = 3):
        # analysis_fps: how often gpt-4o-mini is called (API calls/sec)
        # output_fps: how often annotated frames are emitted to the stream
        self.analysis_fps = analysis_fps
        self.output_fps = output_fps
        self._forwarder: Optional[VideoForwarder] = None
        self._video_track = QueuedVideoTrack()
        self._openai = AsyncOpenAI()
        self._current_label = "STATUS: UNKNOWN | Analyzing scene..."
        self._analyzing = False

    # ── Analysis (called at analysis_fps) ────────────────────────────────────

    async def _analyze_frame(self, frame: av.VideoFrame) -> None:
        if self._analyzing:
            return  # Don't pile up concurrent API calls
        self._analyzing = True
        try:
            img = frame.to_image()
            img.thumbnail((512, 512))  # Resize for faster API processing
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()

            response = await self._openai.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=30,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}",
                                    "detail": "low",
                                },
                            },
                        ],
                    }
                ],
            )
            result = response.choices[0].message.content.strip()
            # Validate format — must start with STATUS:
            if result.startswith("STATUS:"):
                self._current_label = result
                logger.info("[ObstacleDetector] %s", result)
            else:
                logger.warning("[ObstacleDetector] Unexpected format: %s", result)
        except Exception as exc:
            logger.error("[ObstacleDetector] API error: %s", exc)
        finally:
            self._analyzing = False

    # ── Annotation & publish (called at output_fps) ───────────────────────────

    async def _annotate_and_publish(self, frame: av.VideoFrame) -> None:
        try:
            img = frame.to_image().convert("RGB")
            draw = ImageDraw.Draw(img)
            w, h = img.size

            label = self._current_label
            is_blocked = "BLOCKED" in label
            bg_color = (200, 0, 0, 220) if is_blocked else (0, 140, 0, 220)
            text_color = (255, 255, 255)

            # Draw banner at top
            banner_h = max(36, h // 10)
            draw.rectangle([(0, 0), (w, banner_h)], fill=bg_color[:3])

            # Try to use a reasonable font size
            font_size = max(14, banner_h - 10)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                try:
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
                except Exception:
                    font = ImageFont.load_default()

            draw.text((8, (banner_h - font_size) // 2), label, fill=text_color, font=font)

            arr = np.array(img)
            new_frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            await self._video_track.add_frame(new_frame)
        except Exception as exc:
            logger.error("[ObstacleDetector] Annotation error: %s", exc)
            await self._video_track.add_frame(frame)  # fallback: publish raw frame

    # ── VideoProcessorPublisher interface ─────────────────────────────────────

    async def process_video(
        self,
        track: aiortc.VideoStreamTrack,
        participant_id: Optional[str],
        shared_forwarder: Optional[VideoForwarder] = None,
    ) -> None:
        if self._forwarder:
            await self._forwarder.remove_frame_handler(self._analyze_frame)
            await self._forwarder.remove_frame_handler(self._annotate_and_publish)
        self._forwarder = shared_forwarder
        # Two independent handlers at different rates
        self._forwarder.add_frame_handler(
            self._analyze_frame,
            fps=float(self.analysis_fps),
            name="obstacle_analysis",
        )
        self._forwarder.add_frame_handler(
            self._annotate_and_publish,
            fps=float(self.output_fps),
            name="obstacle_annotate",
        )

    def publish_video_track(self) -> aiortc.VideoStreamTrack:
        return self._video_track

    async def stop_processing(self) -> None:
        if self._forwarder:
            await self._forwarder.remove_frame_handler(self._analyze_frame)
            await self._forwarder.remove_frame_handler(self._annotate_and_publish)
            self._forwarder = None

    async def close(self) -> None:
        await self.stop_processing()
        self._video_track.stop()


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt
# gpt-4o-realtime is instructed to read the STATUS banner as ground truth.
# ─────────────────────────────────────────────────────────────────────────────

INSTRUCTIONS = """
You are BlindSight AI, a real-time voice guide for people who are blind or visually impaired.
The user is pointing their phone camera forward as they navigate. You are their eyes.

═══════════════════════════════════════════════════
CRITICAL: READ THE STATUS BANNER IN EVERY FRAME
═══════════════════════════════════════════════════

Every video frame has a coloured STATUS banner at the TOP of the image.
This banner is produced by an accurate AI vision analysis system.
You MUST use this banner as your primary ground truth. It says:

  STATUS: BLOCKED | [description of obstacle]
  STATUS: CLEAR | [description of open path]
  STATUS: UNKNOWN | [when system is still loading]

RED banner = BLOCKED → immediately tell the user what is blocking and to stop.
GREEN banner = CLEAR → tell the user the path is clear and they can move forward.

Do NOT rely on your own interpretation of the raw image. Trust the STATUS banner.

SPEAKING RULES:
- 1-2 short sentences maximum per response. This is real-time speech.
- Deliver path status immediately after every few seconds.
- If RED: "Wardrobe directly ahead, stop." / "Door blocking the path."
- If GREEN: "Path is clear, move forward." / "Open hallway ahead, go."
- No markdown, no lists. Plain spoken language only.
- Calm and clear normally. Firm and urgent for dangers.

VOICE COMMANDS:
- "What do you see?" → read the STATUS banner and describe scene in 2-3 sentences
- "Is the path clear?" → yes or no based on STATUS banner
- "Any hazards?" → report based on STATUS banner + visible dangers
- "Read this" → read all visible text in the image
- "Where am I?" → describe the environment type
- "Describe the person" → describe the nearest visible person

TONE: Calm, trusted, direct. Like a careful friend. Their safety depends on your accuracy.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Agent Factory
# ─────────────────────────────────────────────────────────────────────────────

async def create_agent(**kwargs) -> Agent:
    return Agent(
        edge=getstream.Edge(),
        agent_user=User(name="BlindSight AI", id="blindsight-agent"),
        instructions=INSTRUCTIONS,
        llm=openai.Realtime(
            model="gpt-4o-realtime-preview",
            voice="alloy",
            fps=3,  # Realtime receives annotated frames at 3fps
        ),
        turn_detection=smart_turn.TurnDetection(),
        processors=[
            ObstacleAnnotationProcessor(
                analysis_fps=1,  # gpt-4o-mini called 1x per second
                output_fps=3,    # annotated frames published at 3fps
            )
        ],
    )


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs):
    await agent.create_user()
    call = await agent.create_call(call_type, call_id)
    async with agent.join(call):
        logger.info("Waiting for user to join the call…")
        await agent.wait_for_participant()
        logger.info("User joined — sending greeting")

        await asyncio.sleep(1.0)
        await agent.llm.simple_response(
            text=(
                "Greet the user warmly in one sentence and tell them you are ready to guide them. "
                "Then immediately read the STATUS banner in the current frame and report the path status."
            )
        )

        await agent.finish()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlindSight AI Agent")
    parser.add_argument("--call-type", default="default", help="Stream call type")
    parser.add_argument("--call-id", default="blindsight-live", help="Stream call ID")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    launcher = AgentLauncher(
        create_agent=create_agent,
        join_call=join_call,
        agent_idle_timeout=0,
    )
    runner = Runner(launcher)

    while True:
        try:
            logger.info("Starting BlindSight AI agent (call %s/%s)…", args.call_type, args.call_id)
            runner.run(
                call_type=args.call_type,
                call_id=args.call_id,
                log_level=args.log_level,
                debug=args.debug,
                no_demo=True,
            )
            logger.info("Runner exited cleanly — restarting in 3 s…")
        except KeyboardInterrupt:
            logger.info("Shutting down.")
            break
        except Exception as exc:
            logger.error("Runner crashed: %s — restarting in 5 s…", exc)
            time.sleep(5)
            continue
        time.sleep(3)
