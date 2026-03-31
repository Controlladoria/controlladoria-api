"""
Test configuration for pytest
Adds parent directory to Python path so tests can import modules
"""

import sys
from pathlib import Path

# Add parent directory to Python path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
