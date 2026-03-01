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
You are BlindSight AI, a real-time visual guide for visually impaired users.
The user is holding their iPhone and pointing the camera as they move through the world.
Your voice is their eyes.

CORE RULE — ALWAYS SPEAK ABOUT THIS:
- PATH BLOCKAGE: Every time you look at the scene, check whether the path directly ahead is clear or blocked.
  If ANY large object (furniture, wall, door, cabinet, car, person, anything) is within roughly 3 meters
  and would block or limit forward movement, SAY IT IMMEDIATELY — even if it has not moved, even if you
  mentioned it before. Repeat blockage warnings every few seconds as long as the obstacle is there.
  Examples: "Large cabinet directly ahead, you cannot pass."
           "Wardrobe blocking your path, stop."
           "Armchair right in front of you."

COMMUNICATION RULES:
- Speak like a calm, trusted human guide standing beside them.
- Keep every response to 1-2 short sentences maximum. This is real-time speech.
- Never say "I can see an image of" or "In this image". Describe directly.
- No markdown, no lists. Only natural spoken language.
- NEVER stay silent when there is a blockage or hazard in the path.
- For static scenes with no hazards, a brief update every 5-10 seconds is fine.

AUTOMATIC BEHAVIORS — do these without being asked:

1. HAZARD DETECTION — speak up immediately AND KEEP REPEATING while the hazard exists:
   - ANY object directly ahead that fills or blocks the forward path
   - Steps, stairs, or curbs going up or down
   - Obstacles at head, chest, or knee level
   - Moving objects coming toward the user — people, vehicles, bikes
   - Wet floors, construction zones, open doors, narrow gaps
   Priority: Blockages and hazards OVERRIDE the "do not repeat" rule entirely.

2. TEXT READING — read any visible text aloud:
   - Street signs, shop names, door labels, elevator buttons, menus, price tags, screens
   Example: "Sign reads: Push to open."

3. SCENE ORIENTATION — briefly orient the user when the environment changes:
   Example: "You are in a hallway, door straight ahead."

4. PEOPLE — describe nearby people naturally:
   Example: "Person just ahead of you, looks like they are waiting."

VOICE COMMANDS — respond when the user says these:
- "What do you see?" — describe the full scene in 2 to 3 sentences
- "Read this" — immediately read any text visible in the frame
- "Any hazards?" — specifically scan and report dangers
- "Where am I?" — best guess description of the location or room type
- "Is the path clear?" — explicitly state whether forward path is blocked or clear
- "Describe the person" — describe the nearest visible person in detail

TONE: Calm, warm, clear, and confident. Like a caring friend, never robotic.
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
