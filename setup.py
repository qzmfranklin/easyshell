#!/usr/bin/env python3

import os
import setuptools

# Get the long description from the README file
this_dir = os.path.abspath(os.path.dirname(__file__))
readme_fname = os.path.join(this_dir, 'README.rst')
with open(readme_fname, encoding='utf-8') as f:
    long_description = f.read()

if __name__ == '__main__':
    setuptools.setup(
        name = 'easyshell',
        version = '0.300',
        description = 'Library for creating recursive shells.',
        long_description = long_description,
        url = 'https://github.com/qzmfranklin/easyshell',
        author = 'Zhongming Qu',
        author_email = 'qzmfranklin@gmail.com',
        keywords = [
            'shell'
        ],
        license = [
            'GPL3',
        ],
        packages = [
            'easyshell',
            'easycompleter',
        ],
        install_requires = [
            'terminaltables',
        ],
        classifiers = [
            "Programming Language :: Python :: 3",
            "Intended Audience :: Developers",
            "Operating System :: OS Independent",
        ],
    )
