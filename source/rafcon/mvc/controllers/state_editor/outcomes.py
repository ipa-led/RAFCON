"""
.. module:: state_outcomes
   :platform: Unix, Windows
   :synopsis: A module that holds the controller to list and edit outcomes of a state and to add-remove or edit
     outcome-related transitions.

.. moduleauthor:: Rico Belder


"""

import gtk
import glib
import gobject

from rafcon.statemachine.states.library_state import LibraryState

from rafcon.mvc.controllers.utils.extended_controller import ExtendedController
from rafcon.mvc.controllers.utils.selection import ListSelectionFeatureController
from rafcon.mvc.controllers.utils.tab_key import MoveAndEditWithTabKeyListFeatureController
from rafcon.mvc.models.container_state import ContainerStateModel
from rafcon.mvc.state_machine_helper import insert_self_transition_meta_data

from rafcon.mvc.gui_helper import react_to_event
from rafcon.utils import log

logger = log.get_logger(__name__)

# TODO find out why not editable ID-column cause segfault ->  if sometimes move into widget by tab and enter is pressed


class StateOutcomesListController(ExtendedController, ListSelectionFeatureController):
    """The controller handles the outcomes of one respective state

    The controller allows to add and remove outcomes as well as to add, remove and to modify the related transition.

    The related transition can be set to a sibling-state, to the state it self or to a outcome of the parent.
    Hereby the transition also can switch from pointing to an outcome or to a state. It react to changes in the
    state's respective outcomes-list, transitions-list or change of parent-state and use additionally the focus change
    to update after a modification (e.g. the focus change updates if not observed state-names change).
    """
    ID_STORAGE_ID = 0
    NAME_STORAGE_ID = 1
    CORE_STORAGE_ID = 4
    CORE_PARENT_STORAGE_ID = 5
    MODEL_STORAGE_ID = 6

    def __init__(self, model, view):
        # initiate data base and tree
        # id, name, to-state, to-outcome, name-color, to-state-color, outcome, state, outcome_model
        self.list_store = gtk.ListStore(str, str, str, str, gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT,
                                        gobject.TYPE_PYOBJECT)
        self.tree_view = view['tree_view']
        self._logger = logger

        self.to_state_combo_list = gtk.ListStore(str, str, str)
        self.to_outcome_combo_list = gtk.ListStore(str, str, str)
        # key-outcome_id -> label,  to_state_id,  transition_id
        self.dict_to_other_state = {}
        # key-outcome_id ->  label,  to_outcome_id,  transition_id
        self.dict_to_other_outcome = {}
        # not used at the moment key-outcome_id -> label,  from_state_id,  transition_id
        self.dict_from_other_state = {}  # if widget gets extended

        self._current_editable_with_event = None

        ExtendedController.__init__(self, model, view)
        ListSelectionFeatureController.__init__(self, self.list_store, self.tree_view, logger)
        self.tab_edit_controller = MoveAndEditWithTabKeyListFeatureController(self.tree_view)
        if not model.state.is_root_state:
            self.observe_model(model.parent)

        if self.model.get_sm_m_for_state_m() is not None:
            self.observe_model(self.model.get_sm_m_for_state_m())
        else:
            logger.warning("State model has no state machine model -> state model: {0}".format(self.model))

        self.tree_view.set_model(self.list_store)

    def register_view(self, view):
        """Called when the View was registered

        Can be used e.g. to connect signals. Here, the destroy signal is connected to close the application
        """
        if view['to_state_col'] and view['to_outcome_col'] and view['to_state_combo'] and view['to_outcome_combo']:
            view['to_state_combo'].connect("edited", self.on_to_state_edited)
            view['to_outcome_combo'].connect("edited", self.on_to_outcome_edited)

        view['name_cell'].connect('edited', self.on_name_edited)
        view['name_cell'].connect('editing-started', self.on_editing_started)
        view['name_cell'].connect('editing-canceled', self.on_editing_canceled)

        ListSelectionFeatureController.register_view(self, view)
        self.update()

    def on_editing_started(self, renderer, editable, path):
        """Connects the a handler for the focus-out-event of the current editable

        :param gtk.CellRendererText renderer: The cell renderer who's editing was started
        :param gtk.CellEditable editable: interface for editing the current TreeView cell
        :param str path: the path identifying the edited cell
        """
        if self.view['name_cell'] is renderer:
            self._current_editable_with_event = (editable, editable.connect('focus-out-event', self.on_focus_out))
        else:
            logger.error("Not registered Renderer was used")

    def on_editing_canceled(self, renderer):
        """Disconnects the focus-out-event handler of cancelled editable

        :param gtk.CellRendererText renderer: The cell renderer who's editing was cancelled
        """
        if self._current_editable_with_event is not None:
            self._current_editable_with_event[0].disconnect(self._current_editable_with_event[1])
            self._current_editable_with_event = None

    def on_focus_out(self, entry, event):
        """Applies the changed name

        The default behaviour for the focus out event dismisses the edited name. Therefore we apply the name beforehand.

        :param gtk.Entry entry: The entry that was focused out
        :param gtk.Event event: Event object with information about the event
        """
        if self.tree_view.get_cursor()[0] is None:
            return

        # We have to use idle_add to prevent core dumps:
        # https://mail.gnome.org/archives/gtk-perl-list/2005-September/msg00143.html
        glib.idle_add(self.on_name_edited, entry, self.tree_view.get_cursor()[0], entry.get_text())

    def on_name_edited(self, renderer, path, new_name):
        """Apply the newly entered outcome name it is was changed

        :param gtk.CellRendererText renderer: The cell renderer that was edited
        :param str path: The path string of the renderer
        :param str new_name:
        """
        # Don't do anything if outcome name didn't change
        if new_name == self.list_store[path][self.NAME_STORAGE_ID]:
            return

        outcome_id = self.list_store[path][self.CORE_STORAGE_ID].outcome_id
        outcome = self.model.state.outcomes[outcome_id]
        try:
            outcome.name = new_name
            logger.debug("Outcome name changed to '{0}'".format(outcome.name))
        except (ValueError, TypeError) as e:
            logger.warning("The name of the outcome could not be changed: {0}".format(e))
        self.list_store[path][self.NAME_STORAGE_ID] = outcome.name

    def on_to_state_edited(self, renderer, path, new_state_identifier):
        """Connects the outcome with a transition to the newly set state

        :param gtk.CellRendererText renderer: The cell renderer that was edited
        :param str path: The path string of the renderer
        :param str new_state_identifier: An identifier for the new state that was selected
        """
        outcome_id = int(self.list_store[path][self.ID_STORAGE_ID])
        if outcome_id in self.dict_to_other_state.keys() or outcome_id in self.dict_to_other_outcome.keys():
            transition_parent_state = self.model.parent.state
            if outcome_id in self.dict_to_other_state.keys():
                t_id = int(self.dict_to_other_state[outcome_id][2])
            else:
                t_id = int(self.dict_to_other_outcome[outcome_id][2])
            if new_state_identifier is not None:
                to_state_id = new_state_identifier.split('.')[1]
                if not transition_parent_state.transitions[t_id].to_state == to_state_id:
                    try:
                        transition_parent_state.transitions[t_id].modify_target(to_state=to_state_id)
                    except ValueError as e:
                        logger.warn("The target of transition couldn't be modified: {0}".format(e))
            else:
                try:
                    transition_parent_state.remove_transition(t_id)
                except AttributeError as e:
                    logger.warn("The transition couldn't be removed: {0}".format(e))
        else:  # there is no transition till now
            if new_state_identifier is not None and not self.model.state.is_root_state:
                transition_parent_state = self.model.parent.state
                to_state_id = new_state_identifier.split('.')[1]
                try:
                    t_id = transition_parent_state.add_transition(from_state_id=self.model.state.state_id,
                                                                  from_outcome=outcome_id,
                                                                  to_state_id=to_state_id,
                                                                  to_outcome=None, transition_id=None)
                except (ValueError, TypeError) as e:
                    logger.warn("The transition couldn't be added: {0}".format(e))
                    return

                # add self transition meta data
                if 'self' in new_state_identifier.split('.'):
                    insert_self_transition_meta_data(self.model, t_id, 'outcomes_widget', 'append_to_last_change')

            else:
                logger.debug("outcome-editor got None in to_state-combo-change no transition is added")

    def on_to_outcome_edited(self, renderer, path, new_outcome_identifier):
        """Connects the outcome with a transition to the newly set outcome

        :param gtk.CellRendererText renderer: The cell renderer that was edited
        :param str path: The path string of the renderer
        :param str new_outcome_identifier: An identifier for the new outcome that was selected
        """
        if self.model.parent is None:
            return
        outcome_id = int(self.list_store[path][self.ID_STORAGE_ID])
        transition_parent_state = self.model.parent.state
        if outcome_id in self.dict_to_other_state.keys() or outcome_id in self.dict_to_other_outcome.keys():
            if outcome_id in self.dict_to_other_state.keys():
                t_id = int(self.dict_to_other_state[outcome_id][2])
            else:
                t_id = int(self.dict_to_other_outcome[outcome_id][2])
            if new_outcome_identifier is not None:
                new_to_outcome_id = int(new_outcome_identifier.split('.')[2])
                if not transition_parent_state.transitions[t_id].to_outcome == new_to_outcome_id:
                    to_state_id = self.model.parent.state.state_id
                    try:
                        transition_parent_state.transitions[t_id].modify_target(to_state=to_state_id,
                                                                                to_outcome=new_to_outcome_id)
                    except ValueError as e:
                        logger.warn("The target of transition couldn't be modified: {0}".format(e))
            else:

                transition_parent_state.remove_transition(t_id)
        else:  # there is no transition till now
            if new_outcome_identifier is not None:
                to_outcome = int(new_outcome_identifier.split('.')[2])

                try:
                    self.model.parent.state.add_transition(from_state_id=self.model.state.state_id,
                                                           from_outcome=outcome_id,
                                                           to_state_id=self.model.parent.state.state_id,
                                                           to_outcome=to_outcome, transition_id=None)
                except (ValueError, TypeError) as e:
                    logger.warn("The transition couldn't be added: {0}".format(e))
            else:
                logger.debug("outcome-editor got None in to_outcome-combo-change no transition is added")

    def on_add(self, button, info=None):
        outcome_id = None
        num_success_outcomes = len(self.model.state.outcomes) - 2
        for run_id in range(num_success_outcomes + 1, 0, -1):
            try:
                outcome_id = self.model.state.add_outcome('success' + str(run_id))
                break
            except ValueError as e:
                if run_id == num_success_outcomes:
                    logger.warn("The outcome couldn't be added: {0}".format(e))
                    return
        # Search for new entry and select it
        ctr = 0
        for outcome_row in self.list_store:
            # Compare outcome ids
            if outcome_row[self.CORE_STORAGE_ID].outcome_id == outcome_id:
                self.tree_view.set_cursor(ctr)
                break
            ctr += 1

        return True

    def on_remove(self, button, info=None):

        tree, path = self.tree_view.get_selection().get_selected_rows()
        if path:  # and not self.list_store[path[0][0]][self.CORE_STORAGE_ID].outcome_id < 0 leave this check for the state
            outcome_id = self.list_store[path[0][0]][self.CORE_STORAGE_ID].outcome_id
            try:
                self.model.state.remove_outcome(outcome_id)
                row_number = path[0][0]
                if len(self.list_store) > 0:
                    self.tree_view.set_cursor(min(row_number, len(self.list_store)-1))
                return True
            except AttributeError as e:
                logger.warning("Error while removing outcome: {0}".format(e))

    def on_right_click_menu(self):
        pass

    def update_internal_data_base(self):

        model = self.model

        self.to_state_combo_list.clear()
        self.to_state_combo_list.append([None, None, None])
        self.to_outcome_combo_list.clear()
        self.to_outcome_combo_list.append([None, None, None])
        self.dict_to_other_state.clear()
        self.dict_to_other_outcome.clear()
        self.dict_from_other_state.clear()

        if not model.state.is_root_state:
            # check for "to state combos" -> so all states in parent
            parent_id = model.parent.state.state_id
            for parent_child_state_m in model.parent.states.values():
                if not model.state.state_id == parent_child_state_m.state.state_id:
                    self.to_state_combo_list.append([parent_child_state_m.state.name + "." + parent_child_state_m.state.state_id,
                                                     parent_child_state_m.state.state_id, parent_id])
                else:
                    self.to_state_combo_list.append(["self." + parent_child_state_m.state.state_id,
                                                     parent_child_state_m.state.state_id, parent_id])
            # check for "to outcome combos" -> so all outcomes of parent
            for outcome in model.parent.state.outcomes.values():
                self.to_outcome_combo_list.append(['parent.' + outcome.name + '.' + str(outcome.outcome_id),
                                                   outcome.outcome_id, parent_id])
            for transition_id, transition in model.parent.state.transitions.items():
                # check for "to other state" connections -> so from self-state and self-outcome "external" transitions
                if transition.from_state == model.state.state_id and transition.from_outcome in model.state.outcomes.keys():
                    # check for "to other outcomes" connections -> so to parent-state and parent-outcome "ext" transitions
                    if transition.to_state == model.parent.state.state_id:
                        to_state_id = model.parent.state.state_id
                        to_outcome_name = model.parent.state.outcomes[transition.to_outcome].name
                        self.dict_to_other_outcome[transition.from_outcome] = [to_outcome_name + '.' + str(transition.to_outcome),
                                                                               to_state_id,
                                                                               transition.transition_id]
                    else:  # or to other state
                        if model.parent.states[transition.to_state].state.state_id == self.model.state.state_id:
                            to_state_name = 'self'
                        else:
                            to_state_name = model.parent.states[transition.to_state].state.name
                        self.dict_to_other_state[transition.from_outcome] = [to_state_name + '.' + transition.to_state,
                                                                             '',
                                                                             transition.transition_id]
        if isinstance(model, ContainerStateModel):
            # check for "from other state" connections -> so to self-state and self-outcome "internal" transitions
            for transition_id, transition in model.state.transitions.items():
                if transition.to_state is None:  # no to_state means self
                    if transition.to_outcome in self.dict_from_other_state:
                        self.dict_from_other_state[transition.to_outcome].append([transition.from_state, transition.from_outcome, transition.transition_id])
                    else:
                        self.dict_from_other_state[transition.to_outcome] = [[transition.from_state, transition.from_outcome, transition.transition_id]]

    def update_list_store(self):

        self.list_store.clear()
        for outcome in self.model.state.outcomes.values():
            to_state = None
            if outcome.outcome_id in self.dict_to_other_state.keys():
                to_state = self.dict_to_other_state[outcome.outcome_id][0]
            to_outcome = None
            if outcome.outcome_id in self.dict_to_other_outcome.keys():
                to_outcome = self.dict_to_other_outcome[outcome.outcome_id][0]
                to_state = 'parent'
            self.list_store.append([outcome.outcome_id, outcome.name, to_state, to_outcome,
                                    outcome, self.model.state, self.model.get_outcome_m(outcome.outcome_id)])

        if self.view and self.view['to_state_col'] and self.view['to_state_combo']:
            for cell_renderer in self.view['to_state_col'].get_cell_renderers():
                cell_renderer.set_property("editable", True)
                cell_renderer.set_property("model", self.to_state_combo_list)
                cell_renderer.set_property("text-column", self.ID_STORAGE_ID)
                cell_renderer.set_property("has-entry", False)
        if self.view and self.view['to_outcome_col'] and self.view['to_outcome_combo']:
            for cell_renderer in self.view['to_outcome_col'].get_cell_renderers():
                cell_renderer.set_property("editable", True)
                cell_renderer.set_property("model", self.to_outcome_combo_list)
                cell_renderer.set_property("text-column", self.ID_STORAGE_ID)
                cell_renderer.set_property("has-entry", False)

    def update(self):
        self.update_internal_data_base()
        self.update_list_store()

    def get_state_machine_selection(self):
        # print type(self).__name__, "get state machine selection"
        sm_selection = self.model.get_sm_m_for_state_m().selection
        return sm_selection, sm_selection.outcomes

    @ExtendedController.observe("selection", after=True)
    def state_machine_selection_changed(self, model, prop_name, info):
        if "outcomes" == info['method_name']:
            self.update_selection_sm_prior()

    @ExtendedController.observe("parent", after=True)
    @ExtendedController.observe("outcomes", after=True)
    @ExtendedController.observe("transitions", after=True)
    def outcomes_changed(self, model, prop_name, info):
        self.update()


class StateOutcomesEditorController(ExtendedController):

    def __init__(self, model, view):
        """Constructor
        """
        ExtendedController.__init__(self, model, view)
        self.oc_list_ctrl = StateOutcomesListController(model, view.treeView)

    def register_view(self, view):
        """Called when the View was registered

        Can be used e.g. to connect signals. Here, the destroy signal is connected to close the application
        """

        if view['add_button'] and view['remove_button']:
            view['add_button'].connect("clicked", self.oc_list_ctrl.on_add)
            view['remove_button'].connect("clicked", self.oc_list_ctrl.on_remove)

            if isinstance(self.model.state, LibraryState):
                view['add_button'].set_sensitive(False)
                view['remove_button'].set_sensitive(False)

    def register_adapters(self):
        """Adapters should be registered in this method call

        Each property of the state should have its own adapter, connecting a label in the View with the attribute of
        the State.
        """

    def register_actions(self, shortcut_manager):
        """Register callback methods for triggered actions

        :param rafcon.mvc.shortcut_manager.ShortcutManager shortcut_manager:
        """
        if not isinstance(self.model.state, LibraryState):
            shortcut_manager.add_callback_for_action("delete", self.remove_outcome)
            shortcut_manager.add_callback_for_action("add", self.add_outcome)

    def add_outcome(self, *event):
        if react_to_event(self.view, self.view.treeView['tree_view'], event) and not isinstance(self.model.state, LibraryState):
            return self.oc_list_ctrl.on_add(None)

    def remove_outcome(self, *event):
        if react_to_event(self.view, self.view.treeView['tree_view'], event) and not isinstance(self.model.state, LibraryState):
            return self.oc_list_ctrl.on_remove(None)
