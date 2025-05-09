from google.adk.tools.agent_tool import AgentTool
from src.sub_agents.to_plan.time_finder.agent import time_finder

time_finder_tool=AgentTool(agent=time_finder)