"""Metadados do pacote e dependências compatíveis por versão do Python."""
from setuptools import find_namespace_packages, setup

setup(
    name="achilles-cdp",
    version="2.0.0",
    description="Chrome CDP Application Services for local AI agents",
    author="Pedro Lucas Reis & Reoli Open Source",
    packages=find_namespace_packages(include=["achilles", "achilles.*"]),
    install_requires=[
        "fastapi>=0.110,<0.129; python_version<'3.10'",
        "fastapi>=0.129,<1; python_version>='3.10'",
        "uvicorn>=0.28,<0.40; python_version<'3.10'",
        "uvicorn>=0.40,<1; python_version>='3.10'",
        "playwright>=1.49,<1.59; python_version<'3.10'",
        "playwright>=1.59,<2; python_version>='3.10'",
        "pydantic>=2.6,<3",
        "rich>=13.0.0",
    ],
    extras_require={
        "test": ["httpx>=0.27,<1"],
        "build": ["pyinstaller>=6.4,<7"],
    },
    entry_points={"console_scripts": ["achilles=achilles.cli.app:main"]},
    python_requires=">=3.9",
)
