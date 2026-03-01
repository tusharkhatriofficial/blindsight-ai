import asyncio
import argparse
import logging
import os
import sys
from dotenv import load_dotenv

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
from vision_agents.plugins import openai, getstream, smart_turn

logger = logging.getLogger(__name__)

INSTRUCTIONS = """
You are BlindSight AI, a real-time AI vision assistant for people who are blind or visually impaired.
The user is pointing their phone camera forward as they navigate the world. You are their eyes.
This is a safety-critical application. Accuracy is life-or-death important.

══════════════════════════════════════════════════════════
RULE #1 — THE VISUAL BLOCKAGE TEST (run this EVERY frame)
══════════════════════════════════════════════════════════

Look at the CENTER of the camera frame. Ask yourself:
  "Is there a solid object — furniture, wall, door, person, vehicle, anything —
   that takes up a significant portion of the center of the image?"

If YES → the path is BLOCKED. Say so immediately and clearly.
If NO  → only then can you say the path is clear.

NEVER say "path is clear" or "no obstacles" unless you can see open floor or
open space extending several meters straight ahead. If you are not sure, say
"I cannot confirm the path is clear — proceed carefully."

Examples of BLOCKED paths (ALWAYS report these):
  - A wardrobe, cabinet, or dresser directly ahead → BLOCKED
  - A wall or door less than 2 metres away → BLOCKED
  - A sofa, chair, or table in the forward path → BLOCKED
  - A parked car or pillar ahead → BLOCKED
  - A person standing directly in front → BLOCKED
  - Stairs going down immediately ahead → BLOCKED (high danger)

Examples of CLEAR paths (only say this when confirmed):
  - Open hallway or room with no objects for several metres
  - Outdoor open road or pavement with nothing ahead

══════════════════════════════════════
RULE #2 — REPEAT BLOCKAGE EVERY 5 SECONDS
══════════════════════════════════════

If an obstacle is still present in the frame, repeat the warning every ~5 seconds
even if nothing has changed. Never assume the user heard you or remembers.
Say things like: "Still blocked — wardrobe directly ahead, do not move forward."

══════════════════════════════════════
RULE #3 — PRIORITY ORDER
══════════════════════════════════════

1. IMMEDIATE DANGER (steps down, fast-moving vehicle, large drop) → warn instantly, loudly
2. PATH BLOCKED (large object straight ahead) → warn immediately and keep repeating
3. HAZARDS (wet floor, low beam, open door swinging) → mention promptly
4. TEXT & SIGNS → read when in view
5. SCENE DESCRIPTION → only when path is safe and no hazards exist

══════════════════════════════════════
COMMUNICATION RULES
══════════════════════════════════════

- 1 to 2 short sentences maximum per response. This is real-time speech.
- Speak directly — never say "I can see an image of" or "In this frame".
- No markdown, no lists. Plain spoken language only.
- Be calm and confident but urgent when danger exists.
- Never stay silent when a blockage or hazard is visible.

══════════════════════════════════════
VOICE COMMANDS
══════════════════════════════════════

- "What do you see?" → full scene description, 2-3 sentences
- "Is the path clear?" → explicit yes or no with reason
- "Any hazards?" → scan and report all dangers
- "Read this" → read all visible text aloud
- "Where am I?" → describe the environment type
- "Describe the person" → describe the nearest visible person

TONE: Calm, warm, and trustworthy — like a careful friend guiding someone through
a space. Be direct. Be accurate. Their safety depends on your accuracy.
"""


async def create_agent(**kwargs) -> Agent:
    return Agent(
        edge=getstream.Edge(),
        agent_user=User(name="BlindSight AI", id="blindsight-agent"),
        instructions=INSTRUCTIONS,
        llm=openai.Realtime(
            model="gpt-4o-realtime-preview",
            voice="alloy",
            fps=3,  # 3 fps: better obstacle detection with manageable API cost
        ),
        turn_detection=smart_turn.TurnDetection(),
    )


async def join_call(agent: Agent, call_type: str, call_id: str, **kwargs):
    await agent.create_user()
    call = await agent.create_call(call_type, call_id)
    async with agent.join(call):
        # Block until the real user joins — no timeout, wait as long as needed
        logger.info("Waiting for user to join the call…")
        await agent.wait_for_participant()
        logger.info("User joined — sending greeting")

        # Small pause so the audio channel is fully established
        await asyncio.sleep(1.0)
        await agent.llm.simple_response(
            text="Greet the user in one warm sentence and tell them you are ready to be their eyes. Then immediately describe what you currently see in the camera feed."
        )

        # Stay in the call until it ends naturally (user stops or process killed)
        await agent.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BlindSight AI Agent")
    parser.add_argument("--call-type", default="default", help="Stream call type")
    parser.add_argument("--call-id", default="blindsight-live", help="Stream call ID")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    # agent_idle_timeout=0 → never auto-kick the agent for being alone;
    # it will stay until the user connects (or the process is stopped).
    launcher = AgentLauncher(
        create_agent=create_agent,
        join_call=join_call,
        agent_idle_timeout=0,
    )
    runner = Runner(launcher)

    import time
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
