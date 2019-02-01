# -*- coding: utf-8 -*-
# Copyright (C) 2012-2014 MUJIN Inc
from distutils.core import setup
from distutils.dist import Distribution

setup(
    distclass=Distribution,
    name='MujinPLC',
    version='0.1.0',
    packages=['mujinplc'],
    package_dir={'mujinplc': 'python/mujinplc'},
    scripts=[
    	'bin/mujin_mujinplcpy_runzmqexample.py',
    	'bin/mujin_mujinplcpy_runudpexample.py',
    ],
    license='Apache License, Version 2.0',
    long_description=open('README.md').read(),
)
