from setuptools import setup

import rfr

rfr_classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Programming Language :: Python :: 3",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Topic :: Software Development :: Libraries",
    "Topic :: Utilities",
]

with open("README.md") as fp:
    rfr_long_description = fp.read()

setup(
    name="rfr",
    version=rfr.__version__,
    author="Braden Baird",
    author_email="bradenbdev@gmail.com",
    url="https://github.com/brbaird/rfr",
    py_modules=["rfr"],
    install_requires=['bencode.py'],
    description="Python module that adds fast resume data to torrent files to be used by rtorrent",
    long_description=rfr_long_description,
    long_description_content_type='text/markdown',
    license="GPLv3",
    classifiers=rfr_classifiers,
    python_requires=">=3.6",
)
