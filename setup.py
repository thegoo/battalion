"""Compatibility shim for editable installs with pre-PEP 660 versions of pip."""

from setuptools import find_packages, setup


setup(
    name="battalion-cli",
    version="0.6.1",
    description="Deterministic mission assessment, planning, dispatch, and assurance",
    python_requires=">=3.9",
    packages=find_packages(include=("battalion", "battalion.*")),
    package_data={"battalion": ["attributes.yml"]},
    install_requires=["PyYAML>=6.0,<7.0", "pytest>=8,<10"],
    entry_points={"console_scripts": ["battalion=battalion.cli:main"]},
)
