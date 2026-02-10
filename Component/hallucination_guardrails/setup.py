from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="hallucination_guardrails",
    version="1.0.0",
    author="Wijetunga W.L.A.T.",
    author_email="IT22910936@my.sliit.lk",
    description="Hallucination Detection & Guardrails Component for Modular Multi-Agent Document AI",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[],
    include_package_data=True,
)
