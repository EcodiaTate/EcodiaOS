# /systems/qora/tools/mesa_tools.py

from mesa import Agent, Model, RandomActivation
from mesa.datacollection import DataCollector

# --- AGENT AND MODEL CREATION ---


async def create_agent_class(name, agent_fn):
    """
    Dynamically create a Mesa agent class.
    Args:
        name (str): Agent class name.
        agent_fn (callable): Function with custom agent step logic.
    Returns:
        Mesa Agent subclass.
    """
    return type(name, (Agent,), {"step": agent_fn})


async def create_model(num_agents, agent_class, width=10, height=10):
    """
    Create a basic Mesa model with RandomActivation scheduler.
    Args:
        num_agents (int): Number of agents.
        agent_class: Agent class (from create_agent_class).
        width (int): (Grid width, optional if you use spatial grid).
        height (int): (Grid height).
    Returns:
        Mesa Model instance.
    """

    class CustomModel(Model):
        def __init__(self):
            self.schedule = RandomActivation(self)
            for i in range(num_agents):
                a = agent_class(i, self)
                self.schedule.add(a)
            self.datacollector = DataCollector()

        def step(self):
            self.schedule.step()

    return CustomModel()


async def run_model(model, steps=10):
    """
    Run a Mesa model for a given number of steps.
    Args:
        model: Mesa Model instance.
        steps (int): Number of steps.
    Returns:
        Any: DataCollector or None.
    """
    for _ in range(steps):
        model.step()
    if hasattr(model, "datacollector"):
        return model.datacollector.get_model_vars_dataframe().to_dict()
    return None


async def collect_agent_data(model):
    """
    Collect all agent states after running a model.
    Args:
        model: Mesa Model instance.
    Returns:
        List of agent states.
    """
    return [vars(agent) for agent in model.schedule.agents]
