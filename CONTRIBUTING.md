# Contributing to RSCE

Thank you for your interest in contributing to the **Research Synthesis & Contradiction Engine (RSCE)**! To ensure a smooth and productive collaboration, please follow the guidelines below.

---

## 🛠️ Development Setup

RSCE requires **Python 3.11+** and **Node.js 18+**.

### 1. Clone the Repository
```bash
git clone https://github.com/Laaksh1205/RSCE.git
cd RSCE
```

### 2. Set Up the Backend
Create a virtual environment, activate it, and install the package along with its development dependencies:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (Command Prompt):
.venv\Scripts\activate.bat

# Install package in editable mode with development dependencies
pip install -e ".[dev]"

# (Optional) Install NLP dependencies for scispaCy MeSH Entity Normalization
pip install -e ".[nlp]"
```

Configure your environment variables by copying `.env.example` to `.env` and adding your API keys:
```bash
cp .env.example .env
```

### 3. Set Up the Frontend
```bash
cd frontend
npm install
```

---

## 🧪 Testing

We require all contributions to pass our unit and integration test suite before merging.

* Run the full test suite locally:
  ```bash
  pytest tests/
  ```
* Run tests with verbose output:
  ```bash
  pytest tests/ -v
  ```
* Run a specific test file:
  ```bash
  pytest tests/test_pipeline.py -v
  ```

---

## 🎨 Code Style & Quality

We use [Ruff](https://github.com/astral-sh/ruff) for linting and code formatting.

* Run the linter:
  ```bash
  ruff check .
  ```
* Format your code:
  ```bash
  ruff format .
  ```

---

## 🚀 Submitting Changes

1. **Create a branch** for your feature or bug fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. **Make your changes** and write/update unit tests to cover them.
3. **Run tests and linter** to verify everything passes locally.
4. **Commit your changes** with clear and descriptive commit messages.
5. **Push to your fork** and **open a Pull Request** against the `main` branch.

Thank you for contributing!
