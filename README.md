# Agentic Engineering Design

> Multi-agent LLM framework for conceptual systems engineering and design.

This repository implements the framework described in the paper **"Agentic Large Language Models for Conceptual Systems Engineering and Design"** published in the [Journal of Mechanical Design](https://doi.org/10.1115/1.4070328). It provides a structured multi-agent workflow that guides LLM agents through requirements extraction, functional decomposition, and simulator code generation for engineering design tasks.

## Key Features

- **Multi-Agent System (MAS)**: 9-role orchestrated workflow for comprehensive design
- **Two-Agent System (2AS)**: Simplified Generator-Reflector loop for ablation studies
- **Design-State Graph (DSG)**: JSON-serializable representation bundling requirements, physical embodiments, and Python physics models
- **Modular Architecture**: Plug-and-play LLM backends (OpenAI, Ollama, custom endpoints)
- **Tool Integration**: Web search, arXiv search, Python REPL, graph manipulation tools

## Quick Start

### Option A — Conda (recommended)

```bash
git clone https://github.com/SoheylM/agentic-eng-design.git
cd agentic-eng-design
python bootstrap_env.py          # creates env, installs deps + pre-commit hooks
conda activate agentic-eng-design
cp .env.example .env             # edit with your API keys
```

### Option B — pip only

```bash
git clone https://github.com/SoheylM/agentic-eng-design.git
cd agentic-eng-design
pip install -e .[dev]            # editable install with dev tools
pre-commit install               # set up pre-commit hooks
cp .env.example .env             # edit with your API keys
```

> **Note:** `requirements.txt` is kept for backwards compatibility. All dependency management lives in `pyproject.toml`.

### Configure LLM Backend

Edit `llm_models.py` to use your preferred LLM backend:
- **OpenAI API**: Set `openai_api_key` and `openai_api_base`
- **Local vLLM**: Set `openai_api_base="http://localhost:8000/v1"`
- **Local Ollama**: Set `openai_api_base="http://localhost:11434/v1"`
- **Local SGLang**: Set `openai_api_base="http://localhost:8002/v1"`

## Demo Workflow

### Step 1: Run Experiments

**For Water System (Solar-Powered Water Filtration):**
```bash
python run_pipeline.py --system water --llm reasoning --temp 1.0 --workflow mas --runs 1
```

**For UAM System (eVTOL Aircraft):**
```bash
python run_pipeline.py --system uam --llm reasoning --temp 1.0 --workflow mas --runs 1
```

**For Full Experimental Study:**
```bash
python run_pipeline.py  # Runs all combinations
```

### Step 2: Visualize Results

**For Water System:**
```bash
python visualization/visualize_third_best_dsg.py
```

**For UAM System:**
```bash
python visualization/visualize_uam_dsg.py
```

### Step 3: Display Metrics

**Quick Terminal Display (for demos):**
```bash
python display_metrics.py <batch_id>
# Example: python display_metrics.py 20250615_185047
```

**Generate Detailed Reports:**
```bash
python eval_saved.py --batch-id <batch_id>
# Example: python eval_saved.py --batch-id 20250615_185047
```

**Evaluate All Batches:**
```bash
python eval_all.py
```

## Metrics Explanation

The framework evaluates Design-State Graphs (DSGs) using 7 metrics:

- **M1 (JSON Validity)**: Percentage of valid JSON outputs
- **M2 (Requirements Coverage)**: Percentage of system requirements addressed
- **M3 (Embodiment Presence)**: Percentage of nodes with physical embodiments
- **M4 (Code Compatibility)**: Percentage of generated Python code that executes successfully
- **M5 (Workflow Completion)**: Percentage of runs that complete successfully
- **M6 (Runtime)**: Average execution time in seconds
- **M7 (Node Count)**: Average number of nodes in the final DSG

**Note**: M2 automatically adapts to the system type (water vs UAM) based on the Cahier des Charges requirements.

## IDETC Demo Workflow

For conference demonstrations, follow this sequence:

1. **Show Existing Results** (Water System):
   ```bash
   python visualization/visualize_third_best_dsg.py
   python display_metrics.py 20250615_185047
   ```

2. **Run Live Demo** (UAM System):
   ```bash
   python run_pipeline.py --system uam --llm reasoning --temp 1.0 --workflow mas --runs 1
   ```

3. **Show Live Results**:
   ```bash
   python visualization/visualize_uam_dsg.py
   python display_metrics.py <new_batch_id>
   ```

This demonstrates the framework's capability to handle different engineering design problems with automatic requirement parsing.

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

## Development

This project uses modern Python tooling for code quality:

| Tool | Purpose | Command |
|------|---------|---------|
| [Ruff](https://docs.astral.sh/ruff/) | Linting & formatting | `ruff check .` / `ruff format .` |
| [MyPy](https://mypy.readthedocs.io/) | Static type checking | `mypy .` |
| [Pre-commit](https://pre-commit.com/) | Git hooks for auto-checks | `pre-commit run --all-files` |
| [Pytest](https://docs.pytest.org/) | Testing | `pytest tests/ -v` |

Pre-commit hooks run automatically on `git commit`. To run all checks manually:

```bash
pre-commit run --all-files
```

Configuration lives in `pyproject.toml` (ruff, mypy, pytest) and `.pre-commit-config.yaml`.

## Citation

If you use this work, please cite:

```bibtex
@article{10.1115/1.4070328,
    author = {Massoudi, Soheyl and Fuge, Mark},
    title = {Agentic Large Language Models for Conceptual Systems Engineering and Design},
    journal = {Journal of Mechanical Design},
    volume = {148},
    number = {5},
    pages = {051405},
    year = {2026},
    month = {01},
    doi = {10.1115/1.4070328},
    url = {https://doi.org/10.1115/1.4070328},
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
