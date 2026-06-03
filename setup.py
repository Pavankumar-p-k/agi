from setuptools import setup, find_packages

setup(
    name="jarvis-ai-os",
    version="1.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "aiosqlite",
        "pydantic",
        "pydantic-settings",
        "python-multipart",
        "python-dotenv",
        "httpx",
        "python-jose[cryptography]",
        "passlib[bcrypt]",
        "bcrypt==3.2.0",
        "recharts",
        "lucide-react",
        "ollama",
        "numpy",
        "opencv-python",
    ],
    entry_points={
        "console_scripts": [
            "jarvis=jarvis:main",
        ],
    },
)
