def main() -> None:
    # Import lazily to avoid requiring environment variables at import time
    from .app import main as _main

    _main()

__all__ = ["main"]
