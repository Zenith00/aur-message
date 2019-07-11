import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="aursync",
    version="0.0.1",
    author="Zenith00",
    author_email="Zenith00dev@gmail.com",
    description="Synchronization library for Aurora",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Zenith00/aur-message",
    packages=setuptools.find_packages(exclude=("tests",)),
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
    install_requires=["aioredis", "async-timeout", "hiredis", "jsonpickle"],
)
