#!/usr/bin/env python3
"""
Agentic Engineering Design - Development Environment Setup
Cross-platform setup script for Windows, macOS, and Linux.
"""

import platform
import subprocess
import sys
from pathlib import Path

ENV_NAME = "agentic-eng-design"


def run_command(cmd, check=True, capture_output=True):
    """Run a command and handle errors."""
    try:
        print(f"  Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
        if result.stdout and capture_output:
            print(result.stdout)
        if result.stderr and capture_output:
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"  Error running command: {e}")
        if e.stderr:
            print(f"  Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"  Command not found: {cmd[0]}")
        return False
    else:
        return result.returncode == 0


def check_conda():
    """Check if conda is available."""
    print("Checking for conda...")
    if not run_command(["conda", "--version"], check=False, capture_output=False):
        print("❌ Conda not found. Please install Miniforge first:")
        print("   https://github.com/conda-forge/miniforge")
        print("   Then restart your terminal and run this script again.")
        return False
    print("✅ Conda found\n")
    return True


def check_env_file():
    """Check that .env file exists."""
    env_path = Path(".env")
    example_path = Path(".env.example")
    if not env_path.exists():
        if example_path.exists():
            print("⚠️  No .env file found. Creating from .env.example...")
            env_path.write_text(example_path.read_text())
            print("   → .env created. Please edit it with your API keys before running experiments.\n")
        else:
            print("⚠️  No .env or .env.example found. You will need to create a .env file with your API keys.\n")
    else:
        print("✅ .env file found\n")


def create_environment():
    """Create the conda environment from environment.yml."""
    print("Creating conda environment...")

    env_file = Path("environment.yml")
    if not env_file.exists():
        print(f"❌ Environment file {env_file} not found")
        return False

    result = run_command(["conda", "env", "create", "-f", str(env_file)])

    if not result:
        print("  Environment creation failed. Checking if it already exists...")
        env_check = subprocess.run(["conda", "env", "list"], check=False, capture_output=True, text=True)
        if ENV_NAME in env_check.stdout:
            print(f"  Environment '{ENV_NAME}' already exists. Removing and recreating...")
            if run_command(["conda", "env", "remove", "-n", ENV_NAME, "-y"]):
                return run_command(["conda", "env", "create", "-f", str(env_file)])
            else:
                print("❌ Failed to remove existing environment")
                return False
        else:
            print("❌ Environment creation failed")
            return False

    print(f"✅ Conda environment '{ENV_NAME}' created\n")
    return True


def install_pre_commit():
    """Install pre-commit hooks."""
    print("Installing pre-commit hooks...")
    result = run_command(["conda", "run", "-n", ENV_NAME, "pre-commit", "install"])
    if result:
        print("✅ Pre-commit hooks installed\n")
    return result


def test_setup():
    """Smoke-test that core imports work."""
    print("Testing the setup...")
    test_script = (
        "from data_models import State, DesignState; "
        "from langchain_core.messages import HumanMessage; "
        "print('✅ Core imports successful')"
    )
    return run_command(["conda", "run", "-n", ENV_NAME, "python", "-c", test_script])


def main():
    print("🧠 Setting up Agentic Engineering Design development environment...")
    print("=" * 65)
    print(f"  Detected OS: {platform.system()}")
    print(f"  Python:      {platform.python_version()}\n")

    if not check_conda():
        return 1

    check_env_file()

    if not create_environment():
        return 1

    if not install_pre_commit():
        print("⚠️  Pre-commit hook installation failed (non-fatal)\n")

    test_setup()

    print("\n" + "=" * 65)
    print("🎉 Setup complete!")
    print("=" * 65)
    print("\nNext steps:")
    print(f"  1. Activate the environment:  conda activate {ENV_NAME}")
    print("  2. Edit .env with your API keys (OpenAI, Tavily, LangChain, SerpAPI)")
    print("  3. Configure your LLM backend in llm_models.py")
    print("  4. Run an experiment:")
    print("       python run_pipeline.py --system water --llm reasoning --temp 1.0 --workflow mas --runs 1")
    print("\nUseful commands:")
    print("  ruff check .                         # Lint")
    print("  ruff check --fix .                   # Auto-fix lint issues")
    print("  ruff format .                        # Format code")
    print("  mypy .                               # Type checking")
    print("  pre-commit run --all-files            # Run all pre-commit hooks")
    print("  pytest tests/ -v                     # Run tests")

    return 0


if __name__ == "__main__":
    sys.exit(main())
