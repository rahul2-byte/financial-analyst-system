import asyncio
from agents.orchestration.planner import PlannerAgent
from app.services.llama_cpp_service import LlamaCppService


async def test_planner_new_agents():
    llm = LlamaCppService()
    planner = PlannerAgent(llm_service=llm)

    query = "Deep analysis of RELIANCE including technicals and risks"
    print(f"Testing query: {query}")

    response = await planner.generate_plan(query)
    print(f"Status: {response.status}")
    if response.data:
        print(f"Scope: {response.data.scope}")
        for step in response.data.execution_steps:
            print(
                f"Step {step.step_number}: {step.target_agent} - {step.action} (Deps: {step.dependencies})"
            )
    else:
        print(f"Errors: {response.errors}")


if __name__ == "__main__":
    asyncio.run(test_planner_new_agents())
