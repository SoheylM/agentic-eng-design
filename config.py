"""
Configuration module for the agentic engineering design system.
Handles loading of environment variables and configuration settings.
"""

import os

from dotenv import load_dotenv


class Config:
    """Configuration class for the agentic engineering design system."""

    def __init__(self, env_file: str | None = None):
        """
        Initialize the configuration.

        Args:
            env_file: Optional path to .env file. If None, will look for .env in current directory.
        """
        # Load environment variables
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        # Required API keys
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.serpapi_api_key = os.getenv("SERPAPI_API_KEY")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        self.langchain_api_key = os.getenv("LANGCHAIN_API_KEY")

        # Optional API keys
        self.twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_from_number = os.getenv("TWILIO_FROM_NUMBER")

        # GitHub configuration
        self.github_app_id = os.getenv("GITHUB_APP_ID")
        self.github_app_private_key = os.getenv("GITHUB_APP_PRIVATE_KEY")
        self.github_repository = os.getenv("GITHUB_REPOSITORY")

        # LangSmith configuration
        self.langchain_tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
        self.langchain_endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
        self.langchain_project = os.getenv("LANGCHAIN_PROJECT")

        # Model configuration
        self.embedding_model = "nomic-embed-text"
        self.retrieval_k = 3

        # Validate required configuration
        self._validate_config()

        # Set environment variables for compatibility
        self._set_env_vars()

    def _validate_config(self) -> None:
        """Validate that all required configuration is present."""
        required_vars = {
            "OPENAI_API_KEY": self.openai_api_key,
            "SERPAPI_API_KEY": self.serpapi_api_key,
            "TAVILY_API_KEY": self.tavily_api_key,
            "LANGCHAIN_API_KEY": self.langchain_api_key,
        }

        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing_vars)}\n"
                "Please ensure these are set in your .env file or environment."
            )

    def _set_env_vars(self) -> None:
        """Set environment variables for compatibility with existing code."""
        os.environ["OPENAI_API_KEY"] = self.openai_api_key
        os.environ["SERPAPI_API_KEY"] = self.serpapi_api_key
        os.environ["TAVILY_API_KEY"] = self.tavily_api_key
        os.environ["LANGCHAIN_API_KEY"] = self.langchain_api_key
        os.environ["TWILIO_ACCOUNT_SID"] = self.twilio_account_sid
        os.environ["TWILIO_AUTH_TOKEN"] = self.twilio_auth_token
        os.environ["TWILIO_FROM_NUMBER"] = self.twilio_from_number
        os.environ["GITHUB_APP_ID"] = self.github_app_id
        os.environ["GITHUB_APP_PRIVATE_KEY"] = self.github_app_private_key
        os.environ["GITHUB_REPOSITORY"] = self.github_repository

    def setup_langsmith_tracing(self, project_name: str) -> None:
        """
        Set up LangSmith tracing for a specific project.

        Args:
            project_name: Name of the project to trace in LangSmith
        """
        if not self.langchain_tracing:
            return

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_ENDPOINT"] = self.langchain_endpoint
        os.environ["LANGCHAIN_PROJECT"] = project_name


# Create a global config instance
config = Config()
