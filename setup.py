#!/usr/bin/env python

from setuptools import setup, find_packages

requirements = [line.strip() for line in
                open('requirements_dev.txt', 'r').readlines()]


setup_args = dict(
    name='nsupdate-web',
    version='0.1',
    description='Simple DDNS (dynamic DNS) web API service with nsupdate',
    author="Shell Chen",
    author_email="me@sorz.org",
    url="https://github.com/sorz/nsupdate-web",
    license='MIT',
    packages=find_packages(),
    test_require=requirements,
    entry_points=dict(
        console_scripts=[
            'ddns-server = nsupdate_web.server:main',
        ]
    ),
)

setup(**setup_args)
