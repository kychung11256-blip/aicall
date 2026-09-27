"""Minimal LiveKit worker for the published one-prompt Dograh trial."""
import json
import os

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession
from livekit.plugins import openai


class SalesAgent(Agent):
    def __init__(self, instructions: str):
        super().__init__(instructions=(
            "你係香港粵語 AI 電話助理。先表明 AI 身份同確認對方方便傾。"
            "對方拒絕就禮貌結束；不可捏造價格或承諾。回答精簡。\n"
            + instructions
        ))


server = AgentServer()


@server.rtc_session(agent_name="sales-agent")
async def sales_session(ctx: agents.JobContext):
    metadata = json.loads(ctx.job.metadata or "{}")
    instructions = metadata.get("instructions", "")
    if not isinstance(instructions, str) or not instructions.strip():
        raise ValueError("Missing published Dograh instructions")
    session = AgentSession(
        llm=openai.realtime.GPTLiveModel(voice=os.getenv("OPENAI_VOICE", "marin"))
    )
    await session.start(room=ctx.room, agent=SalesAgent(instructions))
    # Outbound call: wait for the callee to speak first.


if __name__ == "__main__":
    agents.cli.run_app(server)
