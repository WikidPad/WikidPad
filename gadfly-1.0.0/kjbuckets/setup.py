#! /usr/local/bin/python -O

from distutils.core import setup, Extension

setup (name = "kjbuckets",
   version = "2.2",
   ext_modules = [Extension("kjbuckets", ["kjbucketsmodule.c"])])
