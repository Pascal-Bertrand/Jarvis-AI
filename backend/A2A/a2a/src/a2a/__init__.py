import logging

import click
from dotenv import load_dotenv
import google_a2a
from google_a2a.common.types import AgentSkill, AgentCapabilities, AgentCard
from google_a2a.common.server import A2AServer
from a2a.task_manager import MyAgentTaskManager


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", default="localhost")
@click.option("--port", default=10002)
@click.option("--ollama-host", default="http://127.0.0.1:11434")
@click.option("--ollama-model", default=None)
# ...
def main(host, port, ollama_host, ollama_model):
  skill = AgentSkill(
    id="my-project-echo-skill",
    name="Echo Tool",
    description="Echos the input back with the letters reversed",
    tags=["echo", "repeater"],
    #examples=["I will see this echoed back to me"],
    inputModes=["text"],
    outputModes=["text"],
  )
  logging.info(skill)

  capabilities = AgentCapabilities(
        streaming=False,
  )
  agent_card = AgentCard(

    name="Echo Agent",
    description="This agent echos the input back with the letters reversed",
    url=f"http://{host}:{port}/",
    version="0.1.0",
    defaultInputModes=["text"],
    defaultOutputModes=["text"],
    capabilities=capabilities,
    skills=[skill]
  )
  logging.info(agent_card)
  task_manager = MyAgentTaskManager(
    ollama_host=ollama_host,
    ollama_model=ollama_model,
  )
  server = A2AServer(
    agent_card=agent_card,
    task_manager=task_manager,
    host=host,
    port=port,
  )
  server.start()

if __name__ == "__main__":
  main()