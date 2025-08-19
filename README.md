# Agentic Engineering Design

> Multi-agent LLM framework for conceptual systems engineering and design.

This repository implements the framework described in the paper **"Agentic Large Language Models for Conceptual Systems Engineering and Design"** ([arXiv:2507.08619](https://arxiv.org/abs/2507.08619)). It provides a structured multi-agent workflow that guides LLM agents through requirements extraction, functional decomposition, and simulator code generation for engineering design tasks.

## Key Features

- **Multi-Agent System (MAS)**: 9-role orchestrated workflow for comprehensive design
- **Two-Agent System (2AS)**: Simplified Generator-Reflector loop for ablation studies
- **Design-State Graph (DSG)**: JSON-serializable representation bundling requirements, physical embodiments, and Python physics models
- **Modular Architecture**: Plug-and-play LLM backends (OpenAI, Ollama, custom endpoints)
- **Tool Integration**: Web search, arXiv search, Python REPL, graph manipulation tools

## Quick Start

1. **Clone and install**:
```bash
git clone https://github.com/SoheylM/agentic-eng-design.git
cd agentic-eng-design
pip install -r requirements.txt
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. **Run experiments**:
```bash
python run_pipeline.py
```

## Repository Structure

```
agentic-eng-design/
├── agents/                 # Individual agent implementations
├── workflows/              # MAS and 2AS workflow definitions
├── visualization/          # DSG visualization and analysis tools
├── experiment_results/     # Experimental outputs and metrics
├── config.py              # Environment configuration
├── data_models.py         # Pydantic data models
├── llm_models.py          # LLM client setup
└── tools.py               # Agent tool definitions
```

## Citation

If you use this work, please cite:

```bibtex
@article{massoudi2025agentic,
  title={Agentic Large Language Models for Conceptual Systems Engineering and Design},
  author={Massoudi, Soheyl and Fuge, Mark},
  journal={arXiv preprint arXiv:2507.08619},
  year={2025}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.