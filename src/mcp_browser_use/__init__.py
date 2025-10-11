"""
We do not manage multiple sessions in one MCP connection. 

Each agent will have their own MCP connection.

While each agent will connect to this very same mcp_browser_use code, 
they will still connect independently. They can start and stop their MCP server
connections at will without affecting the functioning of the browser. The 
agents are agnostic to whether other agents are currently running.
The MCP for browser use that we develop here should abstract the browser
handling away from the agents.

When a second agent opens a browser, the agent gets its own browser window. IT 
MUST NOT USE THE SAME BROWSER WINDOW! The second agent WILL NOT open another 
browser session.

## Performance Considerations

We do not mind additional overhead from validations. The most important thing is that the code is robust.

## Tip for Debugging

Do you find any obvious errors in the code? Please do rubber duck 
debugging. Imagine you are the first agent that establishes a 
connection. You connect and want to navigate. You call the function 
to go to a website, but probably receive an error, because you have
to open the browser first. Or do you not receive and error and the
MCP server automatically opens a browser? That would also be fine.
Then you open the browse, if not open yet. Then you click 
around a bit. Then another agent 
establishes a separate MCP server connection and does the same. 
Then the first agent is done with his work and closes the connection. 
The second continues working. In this rubber duck 
journey, is there anything that does not work well?
"""

from . import helpers as helpers
__all__ = ["helpers"]