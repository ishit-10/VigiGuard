"""
Entry point for the DMRC PPE Tracking API server.
"""
import os
import sys
import uvicorn

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load config
import yaml
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "config", "backend", "config.yaml")
with open(CONFIG_PATH, 'r') as f:
    config = yaml.safe_load(f)


def main():
    """Start the API server."""
    host = config['app']['host']
    port = config['app']['port']
    debug = config['app']['debug']
    
    print(f"\n{'=' * 60}")
    print(f"  {config['app']['name']} v{config['app']['version']}")
    print(f"{'=' * 60}")
    print(f"  Server: http://{host}:{port}")
    print(f"  API Docs: http://{host}:{port}/docs")
    print(f"  Debug: {debug}")
    print(f"{'=' * 60}\n")
    
    # Avoid uvicorn reload instability in this repo.
    # Config still drives 'debug', but reload is kept off unless explicitly enabled.
    reload_enabled = bool(os.environ.get("DEV_RELOAD", ""))

    uvicorn.run(
        "backend.core.app:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level="info",
    )


if __name__ == "__main__":
    main()