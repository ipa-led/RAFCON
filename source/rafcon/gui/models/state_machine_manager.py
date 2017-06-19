# Copyright (C) 2015-2017 DLR
#
# All rights reserved. This program and the accompanying materials are made
# available under the terms of the Eclipse Public License v1.0 which
# accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
# Annika Wollschlaeger <annika.wollschlaeger@dlr.de>
# Franz Steinmetz <franz.steinmetz@dlr.de>
# Mahmoud Akl <mahmoud.akl@dlr.de>
# Rico Belder <rico.belder@dlr.de>
# Sebastian Brunner <sebastian.brunner@dlr.de>
import os

from gtkmvc import ModelMT
from gtkmvc import Observable

from rafcon.core.state_machine_manager import StateMachineManager
from rafcon.core.storage import storage

from rafcon.gui.models.state_machine import StateMachineModel
import rafcon.gui.singleton

from rafcon.utils.vividict import Vividict
from rafcon.utils import log, storage_utils

logger = log.get_logger(__name__)


SESSION_STORE_FILE = "previous_session_store.json"


class StateMachineManagerModel(ModelMT, Observable):
    """This model class manages a StateMachineManager

    The model class is part of the MVC architecture. It holds the data to be shown (in this case a state machine
    manager).
    Additional to the data of the StateMachineManager its model and the models of state machines hold by those
    these model stores and made observable the selected state machine of the view which have not to be the same
    as the active running one.

    :param StateMachineManager state_machine_manager: The state machine manager to be managed
    """

    # TODO static variable in StateMachineManagerModel
    __sm_manager_creation_counter = 0
    state_machine_manager = None
    selected_state_machine_id = None
    state_machines = {}
    state_machine_mark_dirty = 0
    state_machine_un_mark_dirty = 0
    recently_opened_state_machines = []

    __observables__ = ("state_machine_manager", "selected_state_machine_id", "state_machines",
                       "state_machine_mark_dirty", "state_machine_un_mark_dirty")

    def __init__(self, state_machine_manager, meta=None):
        """Constructor"""
        ModelMT.__init__(self)  # pass columns as separate parameters
        Observable.__init__(self)
        self.register_observer(self)

        assert isinstance(state_machine_manager, StateMachineManager)

        self.state_machine_manager = state_machine_manager
        self.state_machines = {}
        for sm_id, sm in state_machine_manager.state_machines.iteritems():
            self.state_machines[sm_id] = StateMachineModel(sm, self)

        self._selected_state_machine_id = None
        if len(self.state_machines.keys()) > 0:
            self.selected_state_machine_id = self.state_machines.keys()[0]

        if isinstance(meta, Vividict):
            self.meta = meta
        else:
            self.meta = Vividict()

        # check if the sm_manager_model exists several times
        self.__class__.__sm_manager_creation_counter += 1
        if self.__class__.__sm_manager_creation_counter == 2:
            logger.error("Sm_manager_model exists several times!")
            os._exit(0)

    @property
    def core_element(self):
        return self.state_machine_manager

    def delete_state_machine_models(self):
        for sm_id_to_delete in self.state_machines.keys():
            sm_m = self.state_machines[sm_id_to_delete]
            with sm_m.state_machine.modification_lock():
                sm_m.prepare_destruction()
                del self.state_machines[sm_id_to_delete]
                sm_m.destroy()

    @ModelMT.observe("state_machine_manager", after=True)
    def model_changed(self, model, prop_name, info):
        if info["method_name"] == "add_state_machine":
            logger.debug("Add new state machine model ... ")
            for sm_id, sm in self.state_machine_manager.state_machines.iteritems():
                if sm_id not in self.state_machines:
                    logger.debug("Create new state machine model for state machine with id %s", sm.state_machine_id)
                    with sm.modification_lock():
                        self.state_machines[sm_id] = StateMachineModel(sm, self)
                        self.selected_state_machine_id = sm_id
        elif info["method_name"] == "remove_state_machine":
            sm_id_to_delete = None
            for sm_id, sm_m in self.state_machines.iteritems():
                if sm_id not in self.state_machine_manager.state_machines:
                    sm_id_to_delete = sm_id
                    if self.selected_state_machine_id == sm_id:
                        self.selected_state_machine_id = None
                    break

            if sm_id_to_delete is not None:
                logger.debug("Delete state machine model for state machine with id %s", sm_id_to_delete)
                sm_m = self.state_machines[sm_id_to_delete]
                sm_m.prepare_destruction()
                del self.state_machines[sm_id_to_delete]
                sm_m.destroy()
                sm_m.selection.clear()

    def get_state_machine_model(self, state_m):
        """ Get respective state machine model for handed state model

        :param state_m: State model for which the state machine model should be found
        :return: state machine model
        :rtype: rafcon.gui.models.state_machine.StateMachineModel
        """
        return self.state_machines[state_m.state.get_state_machine().state_machine_id]

    def get_selected_state_machine_model(self):
        """ Get selected state machine model

        :return: state machine model
        :rtype: rafcon.gui.models.state_machine.StateMachineModel
        """
        if self.selected_state_machine_id is None:
            return None

        return self.state_machines[self.selected_state_machine_id]

    @property
    def selected_state_machine_id(self):
        """Property for the _selected_state_machine_id field
        :rtype: int
        """
        return self._selected_state_machine_id

    @selected_state_machine_id.setter
    @Observable.observed
    def selected_state_machine_id(self, selected_state_machine_id):
        if selected_state_machine_id is not None:
            if not isinstance(selected_state_machine_id, int):
                raise TypeError("selected_state_machine_id must be of type int")
        self._selected_state_machine_id = selected_state_machine_id

    def clean_recently_opened_state_machines(self):
        """ Check if state machine paths still valid

        If the state machine is no more valid the state machine is removed from the path.
        :return:
        """
        # clean state machines that can not be reached anymore
        sm_to_delete = []
        for sm_path in self.recently_opened_state_machines:
            if not os.path.exists(sm_path):
                sm_to_delete.append(sm_path)
        for sm_path in sm_to_delete:
            self.recently_opened_state_machines.remove(sm_path)

    def update_recently_opened_state_machines(self, state_machine_m):
        sm = state_machine_m.state_machine
        if sm.file_system_path:
            # check if path is in recent path already
            # print "update recent state machine: ", sm.file_system_path
            if sm.file_system_path in self.recently_opened_state_machines:
                del self.recently_opened_state_machines[self.recently_opened_state_machines.index(sm.file_system_path)]
            self.recently_opened_state_machines.insert(0, sm.file_system_path)
            self.clean_recently_opened_state_machines()
            # TODO menu bar is always one step behind the next line would fix it but it is at the wrong place here
            rafcon.gui.singleton.main_window_controller.get_controller('menu_bar_controller').update_open_recent()
        else:
            logger.warning("State machine {0} can not be added to recent open because it has no valid path."
                           "".format(state_machine_m))

    def store_recent_opened_state_machines(self):
        num = rafcon.gui.singleton.global_gui_config.get_config_value('NUMBER_OF_RECENT_OPENED_STATE_MACHINES_STORED')
        rafcon.gui.singleton.global_runtime_config.set_config_value('recently_used',
                                                                    self.recently_opened_state_machines[:num])

    def read_recent_opened_state_machines(self):
        recently_opened_state_machines = rafcon.gui.singleton.global_runtime_config.get_config_value('recently_used', [])
        self.recently_opened_state_machines = recently_opened_state_machines
        self.clean_recently_opened_state_machines()
        rafcon.gui.singleton.main_window_controller.get_controller('menu_bar_controller').update_open_recent()

    def store_session(self):
        session_store_file_json = os.path.join(rafcon.gui.singleton.global_gui_config.path, SESSION_STORE_FILE)
        session_storage_dict = {'open_tabs': [sm_m.meta for sm_m in self.state_machines.itervalues()]}
        storage_utils.write_dict_to_json(session_storage_dict, session_store_file_json)

    def load_session_from_storage(self):
        # TODO this method needs better documentation and to be moved

        session_store_file_json = os.path.join(rafcon.gui.singleton.global_gui_config.path, SESSION_STORE_FILE)
        if not os.path.exists(session_store_file_json):
            logger.info("No session recovery from: " + session_store_file_json)
            return
        session_storage_dict = storage_utils.load_objects_from_json(session_store_file_json, as_dict=True)
        for sm_meta_dict in session_storage_dict['open_tabs']:
            open_last_backup = False
            if 'last_backup' in sm_meta_dict:
                open_last_backup = True
                path = sm_meta_dict['last_backup']['file_system_path']
                # print "### open last backup?", path
                last_backup_time = storage_utils.get_float_time_for_string(sm_meta_dict['last_backup']['time'])
                if 'last_saved' in sm_meta_dict:
                    if last_backup_time < storage_utils.get_float_time_for_string(sm_meta_dict['last_saved']['time']):
                        path = sm_meta_dict['last_saved']['file_system_path']
                        open_last_backup = False
                        # print "### open last saved", path
            elif 'last_saved' in sm_meta_dict:
                path = sm_meta_dict['last_saved']['file_system_path']
                # print "### open last saved", path
            else:
                continue
            state_machine = storage.load_state_machine_from_path(path)
            self.state_machine_manager.add_state_machine(state_machine)
            if open_last_backup:
                state_machine._file_system_path = sm_meta_dict['last_saved']['file_system_path']
                state_machine.marked_dirty = True
