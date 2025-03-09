from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension("acoustid._ext", ["acoustid/ext/*.pyx"])
]

setup(
    ext_modules=cythonize(extensions),
)
