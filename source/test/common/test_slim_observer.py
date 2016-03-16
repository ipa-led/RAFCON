from gtkmvc.observable import Observable
from gtkmvc.slim_observer import SlimObserver
import testing_utils
import pytest


class ObservableTest(Observable):

    def __init__(self):
        Observable.__init__(self)
        self.__first_var = None
        self.observable_test_var = 0

    @property
    def first_var(self):
        return self.__first_var

    @first_var.setter
    @Observable.observed
    def first_var(self, first_var):
        self.__first_var = first_var

    @Observable.observed
    def complex_method(self, param1, param2, param3):
        print param3
        self.observable_test_var = param1 + param2


class ObserverTest(SlimObserver):

    def __init__(self):
        SlimObserver.__init__(self)
        self.test_observable = ObservableTest()
        self.test_observable.add_observer(self, "first_var", self.on_first_var_changed_before,
                                          self.on_first_var_changed_after)
        self.test_observable.add_observer(self, "complex_method", self.on_complex_method_changed_before)
        self.test_value = 0
        self.test_value2 = 0

    def on_first_var_changed_before(self, observable, args):
        self.test_value = args[1]

    def on_first_var_changed_after(self, observable, args):
        pass

    def on_complex_method_changed_before(self, observable, args):
        self.test_value2 = args[1] + args[2]

def test_slim_observer(caplog):
    test_observer = ObserverTest()
    test_observer.test_observable.first_var = 20.0
    assert test_observer.test_value == 20

    test_observer.test_observable.complex_method(1, 3, "Hello world")
    assert test_observer.test_observable.observable_test_var == 4
    assert test_observer.test_value2 == 4

    testing_utils.assert_logger_warnings_and_errors(caplog)


if __name__ == '__main__':
    # test_slim_observer(None)
    pytest.main([__file__])
