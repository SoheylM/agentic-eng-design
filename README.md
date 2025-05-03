# agentic-eng-design

> Agentic LLM framework for conceptual systems engineering and design.

---

## Table of Contents

- [Introduction](#introduction)  
- [Features](#features)  
- [Repository Structure](#repository-structure)  
- [Installation](#installation)  
- [Configuration](#configuration)  
- [Usage](#usage)  
- [Contributing](#contributing)  
- [Citation](#citation)  
- [License](#license)  

---

## Introduction

This repository implements the framework described in the manuscript  
**“Agentic Large Language Models for Conceptual Systems Engineering and Design”**.  
It provides a modular, multi-agent workflow that guides a collection of LLM "agents" through:

1. **Requirements gathering**  
2. **Planning**  
3. **Supervisor validation**  
4. **Proposal generation & refinement**  
5. **Design graph synthesis**

All packaged so you can swap in different LLM backends, add new agents, or hook in additional tools.

---

## Features

- **Multi-agent orchestration** of the engineering design process  
- **Plug-and-play LLM clients** (OpenAI, Ollama, custom endpoints)  
- **Structured prompt templates** for each design phase  
- **Design graph utilities** for adding/updating/removing nodes & edges  
- **Tool integrations**: web search, arXiv search, Python REPL, custom tools  
- **Interactive workflow** with clear hand-off between agents  

---

## Repository Structure

```text
agentic-eng-design/
├── config.py              # Env var loading & tracing
├── llm_models.py          # LLM client instantiation & structured‐output bindings
├── prompts.py             # All prompt templates
├── utils.py               # Helpers (e.g. remove_think_tags, tool‐call processing)
├── data_models.py         # Pydantic & dataclass definitions
├── graph_utils.py         # Graph manipulation & visualization functions
├── tools.py               # @tool wrappers & tool manager setup
├── agents/                # One module per agent node
│   ├── router.py
│   ├── human.py
│   ├── requirements.py
│   ├── planner.py
│   ├── supervisor.py
│   ├── orchestrator.py
│   ├── worker.py
│   ├── generation.py
│   ├── reflection.py
│   ├── ranking.py
│   ├── evolution.py
│   ├── meta_review.py
│   ├── synthesizer.py
│   └── graph_designer.py
├── workflow.py            # Entry point: builds & runs the StateGraph
├── requirements.txt       # Python dependencies
└── README.md
```

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd <repository-name>
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file based on `.env.example` and fill in your API keys.

## Configuration

1. Copy the example environment file and fill in your keys:
```bash
cp .env.example .env
```

2. Edit .env:
```bash
OPENAI_API_KEY=your_openai_key_here
OLLAMA_API_BASE=http://localhost:11434
# any other required variables…
```

## Running the Application

To start the Streamlit application:

```bash
streamlit run app.py
```

This will start a local web server and open your default web browser to the application interface.

## Usage

1. Start by describing your design requirements in the chat interface
2. The assistant will guide you through the design process
3. Use the sidebar to monitor the workflow status
4. When you're ready to move to the planning phase, click the "End Session" button

## Architecture

The application uses a multi-agent workflow powered by LangGraph, with the following components:

- Router: Directs the workflow based on the current state
- Human: Handles user interaction
- Requirements: Processes and structures design requirements
- Planner: Creates design plans
- Supervisor: Oversees the design process
- Worker: Executes specific design tasks
- And more specialized agents for different aspects of the design process

## Contributing

- Open an issue to discuss design changes or new agents/tools. 
- Submit pull requests with tests and documentation updates.
- Please follow the existing code style and add new dependencies to requirements.txt.

## Citation

If you use or build on this work, please cite:
```bash
Massoudi & Fuge, "Agentic Large Language Models for Conceptual Systems Engineering and Design," IDETC 2025.
```

## License

To be determined.