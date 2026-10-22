"""Compatibility shim: `python pipeline.py ...` still works."""
from mapster.__main__ import main

if __name__ == "__main__":
    main()
