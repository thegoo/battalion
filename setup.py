"""Compatibility shim for editable installs with pre-PEP 660 versions of pip."""

from setuptools import find_packages, setup


setup(
    name="battalion-cli",
    version="0.5.0",
    description="Deterministic mission assessment, planning, and dispatch",
    python_requires=">=3.9",
    packages=find_packages(include=("battalion", "battalion.*")),
    package_data={"battalion": ["attributes.yml"]},
    entry_points={"console_scripts": ["battalion=battalion.cli:main"]},
)
