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
It provides a modular, multi-agent workflow that guides a collection of LLM “agents” through:

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
```bash
git clone https://github.com/<your-org>/agentic-engineering-design.git
cd agentic-engineering-design
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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

## Usage
Run the interactive design workflow:

```bash
python workflow.py
```

You will be prompted to enter an initial project request (e.g. “Build a solar-powered water filtration system”).
The system will then iterate through requirements, planning, proposal generation, and graph synthesis.


## Contributing

- Open an issue to discuss design changes or new agents/tools. 
- Submit pull requests with tests and documentation updates.
- Please follow the existing code style and add new dependencies to requirements.txt.

## Citation

If you use or build on this work, please cite:
```bash
Massoudi & Fuge, “Agentic Large Language Models for Conceptual Systems Engineering and Design,” IDETC 2025.
```

## License

To be determined.