import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="tango",
    version="0.5.8",
    author="John Sundh",
    author_email="john.sundh@scilifelab.se",
    description="A package to assign taxonomy to metagenomic contigs",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/johnne/tango",
    packages=["tango"],
    entry_points={'console_scripts': ['tango = tango.__main__:main']},
    scripts=["tango/evaluate_tango.py"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
