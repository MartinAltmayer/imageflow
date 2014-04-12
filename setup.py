from distutils.core import setup
setup(name="PyQt Image Flow",
      version="0.9",
      description="Easy to use and highly configurable image flow for PyQt.",
      author="Martin Altmayer",
      author_email="martin.altmayer@web.de",
      url="http://www.github.com/MartinAltmayer/ImageFlow/",
      license="GPL v3",
      packages=['imageflow'],
      package_data={'imageflow': ['process-working.png']}
      #data_files=[('imageflow', ['imageflow/process-working.png'])],
)