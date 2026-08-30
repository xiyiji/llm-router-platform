"""Root entry point: start the LLM Router & Execution Platform."""

from app.main import app, run  # noqa: F401

if __name__ == "__main__":
    run()
