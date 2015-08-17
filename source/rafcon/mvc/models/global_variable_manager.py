from gtkmvc import ModelMT
from rafcon.utils.vividict import Vividict
import rafcon.statemachine.singleton


class GlobalVariableManagerModel(ModelMT):

    global_variable_manager = rafcon.statemachine.singleton.global_variable_manager

    __observables__ = ("global_variable_manager",)

    def __init__(self, meta=None):
        """Constructor
        """

        ModelMT.__init__(self)  # pass columns as separate parameters

        if isinstance(meta, Vividict):
            self.meta = meta
        else:
            self.meta = Vividict()