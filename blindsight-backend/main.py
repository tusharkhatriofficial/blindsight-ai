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
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

# ── Startup env validation ─────────────────────────────────────────────────────
_REQUIRED_ENV = ["OPENAI_API_KEY", "STREAM_API_KEY", "STREAM_API_SECRET"]
_missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
if _missing:
    print(
        f"\n[BlindSight AI] Missing required env vars: {', '.join(_missing)}\n",
        file=sys.stderr,
    )
    sys.exit(1)

from vision_agents.core import User, Agent, AgentLauncher, Runner
from vision_agents.core.processors import VideoProcessor
from vision_agents.core.utils.video_forwarder import VideoForwarder
from vision_agents.plugins import openai as va_openai, getstream, smart_turn

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Scene Analysis Processor
# Captures one frame per second, sends it to gpt-4o-mini for ACCURATE scene
# analysis, then triggers simple_response so the realtime model speaks it.
# ─────────────────────────────────────────────────────────────────────────────

VISION_PROMPT = (
    "You are a navigation assistant for a blind person. "
    "Look at this camera image very carefully.\n"
    "Is the forward path BLOCKED or CLEAR?\n"
    "BLOCKED = a solid large object (wardrobe, wall, door, cabinet, furniture, "
    "person, car, sofa, table) fills the centre of the image and physically "
    "prevents moving forward.\n"
    "CLEAR = open floor or open space is visible ahead for several metres. "
    "A road, hallway, pavement, or empty room.\n\n"
    "Reply in this EXACT format (one line only, no extra words):\n"
    "BLOCKED: wardrobe fills the entire view\n"
    "CLEAR: open hallway ahead\n"
    "BLOCKED: closed wooden door right in front\n"
    "CLEAR: road stretching forward\n"
    "Use what you actually see. Be specific."
)


class SceneAnalysisProcessor(VideoProcessor):
    """
    Calls gpt-4o-mini once per second to get accurate scene analysis,
    then triggers the realtime agent to speak the result.
    """

    name = "scene_analysis"

    def __init__(self, analysis_fps: int = 1):
        self.analysis_fps = analysis_fps
        self._forwarder: Optional[VideoForwarder] = None
        self._openai = AsyncOpenAI()
        self._agent = None
        self._analyzing = False
        self._last_spoken_time = 0.0
        self._last_result_type: Optional[str] = None  # "BLOCKED" or "CLEAR"
        self._reminder_interval = 12.0  # repeat reminder every 12s even if no change

    def attach_agent(self, agent) -> None:
        """Called by the framework to give access to the agent."""
        self._agent = agent
        logger.info("[SceneAnalysis] Attached to agent ✓")

    async def process_video(
        self,
        track: aiortc.VideoStreamTrack,
        participant_id: Optional[str],
        shared_forwarder: Optional[VideoForwarder] = None,
    ) -> None:
        if shared_forwarder is None:
            logger.warning("[SceneAnalysis] shared_forwarder is None, skipping")
            return

        # Remove previous handler if re-entering (track switch)
        if self._forwarder is not None:
            try:
                await self._forwarder.remove_frame_handler(self._handle_frame)
            except Exception:
                pass

        self._forwarder = shared_forwarder
        self._forwarder.add_frame_handler(
            self._handle_frame,
            fps=float(self.analysis_fps),
            name="scene_analysis",
        )
        logger.info("[SceneAnalysis] Frame handler registered at %dfps ✓", self.analysis_fps)

    async def _handle_frame(self, frame: av.VideoFrame) -> None:
        # Skip if already analyzing or too soon to speak again
        if self._analyzing or self._agent is None:
            return
        now = time.monotonic()
        if now - self._last_spoken_time < self._min_speak_interval:
            return

        self._analyzing = True
        try:
            # Convert frame to JPEG for API
            img = frame.to_image()
            img.thumbnail((512, 512))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()

            response = await self._openai.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=25,
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
            logger.info("[SceneAnalysis] gpt-4o-mini result: %s", result)

            # Determine result type
            if result.startswith("BLOCKED"):
                result_type = "BLOCKED"
                detail = result[len("BLOCKED:"):].strip() if ":" in result else result
                spoken = f"Say exactly this to the user, nothing else: '{detail}, stop.'"
            elif result.startswith("CLEAR"):
                result_type = "CLEAR"
                detail = result[len("CLEAR:"):].strip() if ":" in result else result
                spoken = f"Say exactly this to the user, nothing else: 'Path is clear, {detail}, move forward.'"
            else:
                return  # Unexpected format, skip

            now = time.monotonic()
            type_changed = result_type != self._last_result_type
            time_since_last = now - self._last_spoken_time

            # Speak only if scene changed OR reminder interval elapsed
            if type_changed or time_since_last >= self._reminder_interval:
                self._last_result_type = result_type
                self._last_spoken_time = now
                await self._agent.llm.simple_response(text=spoken)

        except Exception as exc:
            logger.error("[SceneAnalysis] Error: %s", exc)
        finally:
            self._analyzing = False

    async def stop_processing(self) -> None:
        if self._forwarder is not None:
            try:
                await self._forwarder.remove_frame_handler(self._handle_frame)
            except Exception:
                pass
            self._forwarder = None

    async def close(self) -> None:
        await self.stop_processing()


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — gpt-4o-realtime is the voice layer
# It will receive scene results via simple_response and speak them
# ─────────────────────────────────────────────────────────────────────────────

INSTRUCTIONS = """
You are BlindSight AI, a real-time voice navigation guide for people who are blind or visually impaired.

Your role:
- You receive accurate scene analysis results via system messages.
- Speak them to the user in plain, clear, 1-sentence speech.
- If the scene says BLOCKED: tell the user what is in the way, firmly.
- If the scene says CLEAR: tell the user they can move forward.

Additional behaviors:
- Respond to voice commands naturally.
- "What do you see?" → repeat the last scene analysis
- "Is the path clear?" → yes or no with reason
- "Read this" → read any visible text
- "Where am I?" → describe the environment

TONE: Calm, warm, direct. Like a caring guide. 1-2 sentences maximum per response.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Agent and Call
# ─────────────────────────────────────────────────────────────────────────────

async def create_agent(**kwargs) -> Agent:
    return Agent(
        edge=getstream.Edge(),
        agent_user=User(name="BlindSight AI", id="blindsight-agent"),
        instructions=INSTRUCTIONS,
        llm=va_openai.Realtime(
            model="gpt-4o-realtime-preview",
            voice="alloy",
            fps=1,  # Low fps for realtime - scene analysis handles detection
        ),
        turn_detection=smart_turn.TurnDetection(),
        processors=[
            SceneAnalysisProcessor(analysis_fps=1),
        ],
    )


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs):
    await agent.create_user()
    call = await agent.create_call(call_type, call_id)
    async with agent.join(call):
        logger.info("Waiting for user to join…")
        await agent.wait_for_participant()
        logger.info("User joined")

        await asyncio.sleep(1.0)
        await agent.llm.simple_response(
            text="Greet the user warmly in one sentence and tell them you're ready to guide them safely."
        )

        await agent.finish()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlindSight AI Agent")
    parser.add_argument("--call-type", default="default")
    parser.add_argument("--call-id", default="blindsight-live")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    launcher = AgentLauncher(
        create_agent=create_agent,
        join_call=join_call,
        agent_idle_timeout=0,
    )
    runner = Runner(launcher)

    while True:
        try:
            logger.info("Starting BlindSight AI (call %s/%s)…", args.call_type, args.call_id)
            runner.run(
                call_type=args.call_type,
                call_id=args.call_id,
                log_level=args.log_level,
                debug=args.debug,
                no_demo=True,
            )
            logger.info("Runner exited — restarting in 3s…")
        except KeyboardInterrupt:
            logger.info("Shutting down.")
            break
        except Exception as exc:
            logger.error("Runner crashed: %s — restarting in 5s…", exc)
            time.sleep(5)
            continue
        time.sleep(3)
