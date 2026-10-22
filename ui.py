"""Compatibility shim: `python ui.py` opens the control panel."""
import sys
from mapster.__main__ import main

if __name__ == "__main__":
    sys.argv[1:] = ["ui"]
    main()
