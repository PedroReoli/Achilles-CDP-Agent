from setuptools import setup, find_packages

setup(
    name="achilles-cdp",
    version="1.0.0",
    description="Autonomous Agentic Chrome DevTools Protocol (CDP) Bridge & Security/API Engine",
    author="Pedro Lucas Reis & Reoli Open Source",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.110.0",
        "uvicorn>=0.28.0",
        "playwright>=1.42.0",
        "pydantic>=2.6.0",
        "typer>=0.9.0",
        "rich>=13.7.0",
    ],
    entry_points={
        "console_scripts": [
            "achilles = achilles.cli.app:main",
        ],
    },
    python_requires=">=3.9",
)
