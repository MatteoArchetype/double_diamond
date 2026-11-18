"""Run the complete suite, including pytest fixtures and crash recovery tests."""
from pathlib import Path
import sys

if __name__ == '__main__':
    try:
        import pytest
    except ImportError:
        sys.exit('Install test dependencies first: python -m pip install -r requirements-test.txt')
    sys.exit(pytest.main([str(Path(__file__).parent / 'tests'), '-q']))
