"""
.. module:: script
   :platform: Unix, Windows
   :synopsis: A module to represent the script file for each state in a state machine

.. moduleauthor:: Sebastian Brunner


"""

from gtkmvc import Observable


class Script(Observable):

    """A class for representing the script file for each state in a state machine

    It inherits from Observable to make a change of its fields observable.

    :ivar _path: the path where the script resides
    :ivar _filename: the full name of the script file
    :ivar _compiled_module: holds the compiled module defined in the script file

    """

    def __init__(self, path=None, filename=None):

        Observable.__init__(self)

        self._path = path
        self._filename = filename
        self._compiled_module = None

    def load_module(self):
        """Loads the module given by the path and the filename

        """
        #TODO: implement
        pass

    def build_module(self):
        """Builds the module given by the path and the filename

        """
        #TODO: implement
        pass

#########################################################################
# Properties for all class fields that must be observed by gtkmvc
#########################################################################

    @property
    def path(self):
        """Property for the _path field

        """
        return self._path

    @path.setter
    @Observable.observed
    def path(self, path):
        if not isinstance(path, str):
            raise TypeError("path must be of type str")

        self._path = path

    @property
    def filename(self):
        """Property for the _filename field

        """
        return self._filename

    @filename.setter
    @Observable.observed
    def filename(self, filename):
        if not isinstance(filename, str):
            raise TypeError("filename must be of type str")

        self._filename = filename

    @property
    def compiled_module(self):
        """Property for the _compiled_module field

        """
        return self._compiled_module

    # this setter should actually never be called as the module will be compiled by the build_module() function
    @compiled_module.setter
    @Observable.observed
    def compiled_module(self, compiled_module):
        self._compiled_module = compiled_module