#if not os.environ.get("OPENAI_API_KEY"):
#    raise ValueError("Please set OPENAI_API_KEY environment variable")

#LLM_MODEL = "gpt-4o-mini"
#LLM_TEMPERATURE = 0

#from tool_manager import ToolManager
from os_en_vars import OSEnvVars

# Global booleans
I_want_trace = True

# Define environment variables
OSEV = OSEnvVars()
OSEV.load_api_keys()
if I_want_trace:
    OSEV.langsmith_trace("IDETC25-MassoudiFuge-v2")

EMBEDDING_MODEL = "nomic-embed-text"
RETRIEVAL_K = 3