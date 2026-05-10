"""
setup.py — Install JARVIS CLI as a system command

Usage:
    pip install -e .          # editable install
    jarvis status             # now works from anywhere
    jarvis chat
    jarvis think "text"
"""
from setuptools import setup, find_packages

setup(
    name             = "jarvis-autonomous",
    version          = "4.0.0",
    description      = "JARVIS Autonomous 4-Layer Intelligence System",
    author           = "Pavan",
    python_requires  = ">=3.10",
    packages         = find_packages(),
    install_requires = [
        "fastapi>=0.109.0",
        "uvicorn>=0.27.0",
        "httpx>=0.26.0",
        "pydantic>=2.5.0",
    ],
    entry_points = {
        "console_scripts": [
            "jarvis = cli.jarvis_cli:main",
        ],
    },
    classifiers = [
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
