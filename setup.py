# Legacy setup.py — kept for compatibility.
# All dependency declarations live in pyproject.toml.
# pip install -e . reads from pyproject.toml automatically with modern pip.
from setuptools import setup, find_packages

setup(
    name="jarvis-ai",
    version="1.1.0",
    packages=find_packages(),
    install_requires=[],  # deps defined in pyproject.toml
    entry_points={
        "console_scripts": [
            "jarvis=jarvis:main",
        ],
    },
)
