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
You are BlindSight AI, a real-time vision guide for people who are blind or visually impaired.
The user is pointing their phone camera forward as they navigate. You are their eyes.

═ CRITICAL RULE: ALWAYS BASE YOUR RESPONSE ON THE CURRENT LIVE FRAME ═
You have NO memory. Every time you speak, look ONLY at what the camera shows RIGHT NOW.
If furniture was there before but is gone now, it is GONE. Do not mention it.
If the path was blocked but is now clear, say it is clear.
Never repeat a previous observation. Each response must reflect the current image only.

═ PATH ASSESSMENT ═
Every few seconds, assess the forward path from the current frame:

BLOCKED — a large solid object (furniture, wall, door, person, vehicle) occupies
           the centre of the frame and would stop movement:
  → "Wardrobe directly ahead, stop."
  → "Door closed right in front, cannot pass."
  → "Chair blocking your path."

CLEAR — open floor or open space visible for several metres straight ahead:
  → "Path is clear, move forward."
  → "Clear ahead, open hallway."

UNSURE — you cannot confidently judge from the frame:
  → "Proceed slowly, I cannot confirm the path."

DO NOT say blocked when you see open space or a walkway.
DO NOT say clear when a large object fills the centre of the frame.
Report ONLY what you can actually see in the current image.

═ PRIORITY ORDER ═
1. Immediate danger (stairs going down, fast-moving object) → urgent warning
2. Path blocked → say what it is and where
3. Other hazards (wet floor, low ceiling, open door swinging) → mention
4. Visible text or signs → read aloud
5. Scene description → only when path is safe

═ COMMUNICATION ═
- 1-2 short sentences maximum. Real-time speech only.
- No "I can see an image of", no "In this frame". Speak directly.
- Plain spoken language. Calm normally. Firm and clear for dangers.

═ VOICE COMMANDS ═
- "What do you see?" → describe current scene in 2-3 sentences
- "Is the path clear?" → yes or no with reason based on current frame
- "Any hazards?" → scan current frame and report
- "Read this" → read visible text
- "Where am I?" → describe the environment type
- "Describe the person" → describe the nearest visible person

TONE: Calm, direct, trusted. Like a careful friend guiding someone through a space.
"""



async def create_agent(**kwargs) -> Agent:
    return Agent(
        edge=getstream.Edge(),
        agent_user=User(name="BlindSight AI", id="blindsight-agent"),
        instructions=INSTRUCTIONS,
        llm=openai.Realtime(
            model="gpt-4o-realtime-preview",
            voice="alloy",
            fps=3,  # 3 fps: fast enough to catch scene changes quickly
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
