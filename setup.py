from distutils.core import setup


setup(name="PyQt Image Flow",
      version="1.0",
      description="Easy to use and highly configurable image flow for PyQt.",
      author="Martin Altmayer",
      author_email="martin.altmayer@web.de",
      url="http://www.github.com/MartinAltmayer/ImageFlow/",
      license="GPL v3+",
      packages=['imageflow'],
      package_data={'imageflow': ['process-working.png']},
      classifiers = ["Environment :: X11 Applications :: Qt",
                     "Intended Audience :: Developers",
                     "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
                     "Programming Language :: Python :: 3",
                     "Topic :: Multimedia :: Graphics",
                     "Topic :: Software Development :: User Interfaces"],
)   