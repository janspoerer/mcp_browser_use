# %%

import asyncio
from mcp_agent.core.fastagent import FastAgent

# Initialize FastAgent with a descriptive name
fast = FastAgent("My Agent")

# Define the agent using the decorator, with user to fill in the instruction
# The servers parameter points to the MCP server "mcp_browser_use"
# use_history=True ensures conversation history is maintained
instruction = "Your specific instruction here"  # User to replace with actual task

@fast.agent(
    instruction=instruction,
    servers=["mcp_browser_use"],
    use_history=True,
    # Additional parameters like model can be added if needed
)
async def my_agent_func():
    pass  # Function may be empty as agent logic is handled internally

async def main():
    # Run the agent in a context, getting the agent object
    async with fast.run() as agent:
        max_iterations = 100
        for i in range(max_iterations):
            # Determine input: initial for first iteration, continuation for others
            if i == 0:
                input_text = "Start the task"  # Placeholder; user to define initial goal
            else:
                input_text = "Continue"  # Placeholder; adjust based on agent behavior
            # Call the agent with the input, getting the response
            response = await agent(input_text)
            # Check for completion signal; here assumed as "DONE" in response
            # User may need to adjust based on actual agent output
            if "DONE" in response:
                print("Goal reached.")
                break
            # Log the response for visibility
            print(f"Iteration {i+1}: {response}")
            # Placeholder for history management; user to implement truncation logic
            # Example: if agent has history attribute, agent.history = truncate_history(agent.history)
        else:
            print("Max iterations reached without completing the goal.")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())



# %%