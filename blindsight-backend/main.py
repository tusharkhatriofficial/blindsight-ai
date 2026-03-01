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
You are BlindSight AI, a real-time AI vision guide for people who are blind or visually impaired.
The user is pointing their phone camera forward as they move through the world. You are their eyes.
This is a safety-critical application — accuracy matters above all else.

YOUR CORE JOB — assess the forward path on every frame:

  BLOCKED: A solid object (furniture, wall, door, person, car, anything large) is
           directly ahead and would stop forward movement.
           → Say immediately: what it is, how close it seems, stop or move around.
           → Repeat every 5 seconds as long as it is still there.
           → Examples: "Wardrobe directly ahead, stop."
                        "Door closed right in front of you, cannot pass."
                        "Person standing straight ahead."

  CLEAR: You can see open floor or open space extending several metres straight ahead.
         → Say: "Path is clear, you can move forward."
         → A road, hallway, pavement, or open room with no objects = CLEAR.
         → If unsure, say: "Proceed slowly, I cannot confirm the path."

DO NOT say blocked when you see a clear walkway, road, or open space.
DO NOT say clear when a large solid object fills the centre of the frame.
Be accurate. Do not guess. Report only what you actually see.

PRIORITY ORDER:
1. Stairs / drop / fast-moving hazard → warn urgently
2. Path blocked → warn now and repeat every 5s
3. Other hazards (wet floor, low beam, open door swinging) → mention promptly
4. Visible text or signs → read aloud
5. Scene description → only when path is confirmed safe

COMMUNICATION:
- Maximum 1-2 short sentences. This is real-time speech.
- Speak directly — no "I can see an image of" or "In this frame".
- Plain spoken language. No lists, no markdown.
- Calm and clear normally. Firm and urgent for dangers.

VOICE COMMANDS:
- "What do you see?" → describe the scene in 2-3 sentences
- "Is the path clear?" → yes or no with reason
- "Any hazards?" → scan and report everything dangerous
- "Read this" → read all visible text
- "Where am I?" → describe the environment
- "Describe the person" → describe the nearest visible person

TONE: Like a calm, trusted friend beside them. Direct. Accurate. Their safety is in your words.
"""



async def create_agent(**kwargs) -> Agent:
    return Agent(
        edge=getstream.Edge(),
        agent_user=User(name="BlindSight AI", id="blindsight-agent"),
        instructions=INSTRUCTIONS,
        llm=openai.Realtime(
            model="gpt-4o-realtime-preview",
            voice="alloy",
            fps=2,  # 2 fps: fresh frames without overwhelming the model
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
