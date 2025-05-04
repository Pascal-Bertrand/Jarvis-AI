import google_a2a
from google_a2a.common.types import AgentSkill

def main():
  skill = AgentSkill(
    id="my-project-echo-skill",
    name="Echo Tool",
    description="Echos the input given",
    tags=["echo", "repeater"],
    examples=["I will see this echoed back to me"],
    inputModes=["text"],
    outputModes=["text"],
  )
  print(skill)

if __name__ == "__main__":
  main()