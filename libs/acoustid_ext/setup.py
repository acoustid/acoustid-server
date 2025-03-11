from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "acoustid_ext.fingerprint",
        sources=["src/acoustid_ext/fingerprint.pyx"],
    )
]

setup(
    name="acoustid_ext",
    version="0.1.0",
    packages=["acoustid_ext"],
    package_dir={"": "src"},
    ext_modules=cythonize(extensions, language_level="3"),
)
