# Copyright (C) 2015-2018 DLR
#
# All rights reserved. This program and the accompanying materials are made
# available under the terms of the Eclipse Public License v1.0 which
# accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
# Annika Wollschlaeger <annika.wollschlaeger@dlr.de>
# Benno Voggenreiter <benno.voggenreiter@dlr.de>
# Franz Steinmetz <franz.steinmetz@dlr.de>
# Lukas Becker <lukas.becker@dlr.de>
# Mahmoud Akl <mahmoud.akl@dlr.de>
# Matthias Buettner <matthias.buettner@dlr.de>
# Rico Belder <rico.belder@dlr.de>
# Sebastian Brunner <sebastian.brunner@dlr.de>

"""
.. module:: state_machines_editor
   :synopsis: A module that holds the controller with the interface to the state machines notebook.

"""

import collections
import copy
import gtk

import rafcon.core.singleton
from rafcon.core.states.hierarchy_state import HierarchyState
from rafcon.gui.config import global_gui_config
from rafcon.gui.controllers.graphical_editor import GraphicalEditorController
from rafcon.gui.controllers.utils.extended_controller import ExtendedController
from rafcon.gui.helpers import text_formatting
from rafcon.gui.helpers.label import draw_for_all_gtk_states
from rafcon.gui.models.state_machine import StateMachineModel, StateMachine
from rafcon.gui.models.state_machine_manager import StateMachineManagerModel
from rafcon.gui.utils import constants
from rafcon.gui.utils.dialog import RAFCONButtonDialog
from rafcon.gui.views.graphical_editor import GraphicalEditorView, GL_ENABLED
from rafcon.gui.views.state_machines_editor import StateMachinesEditorView
from gtk.gdk import SHIFT_MASK, CONTROL_MASK
from rafcon.gui.helpers.label import create_image_menu_item
from rafcon.utils import log

logger = log.get_logger(__name__)

GAPHAS_AVAILABLE = True
try:
    from rafcon.gui.views.graphical_editor_gaphas import GraphicalEditorView as GraphicalEditorGaphasView
    from rafcon.gui.controllers.graphical_editor_gaphas import GraphicalEditorController as \
        GraphicalEditorGaphasController
except ImportError as e:
    logger.warn("The Gaphas graphical editor is not supported due to missing libraries: {0}".format(e.message))
    GAPHAS_AVAILABLE = False

ROOT_STATE_NAME_MAX_CHARS = 25


def create_tab_close_button(callback, *additional_parameters):
    close_label = gtk.Label()
    close_label.set_markup('<span font_desc="%s %s">&#x%s;</span>' % (constants.ICON_FONT, constants.FONT_SIZE_SMALL,
                                                                      constants.BUTTON_CLOSE))
    close_button = gtk.Button()
    close_button.set_size_request(width=constants.GRID_SIZE*3, height=constants.GRID_SIZE*3)
    close_button.set_relief(gtk.RELIEF_NONE)
    close_button.set_focus_on_click(True)
    close_button.add(close_label)

    close_button.connect('released', callback, *additional_parameters)

    return close_button


def create_tab_header(title, close_callback, right_click_callback, *additional_parameters):
    def handle_click(widget, event, *additional_parameters):
        """Calls `callback` in case the mouse button was pressed"""
        if event.button == 2 and close_callback:
            close_callback(event, *additional_parameters)
        if event.button == 3 and right_click_callback:
            right_click_callback(event, *additional_parameters)

    label = gtk.Label(title)
    close_button = create_tab_close_button(close_callback, *additional_parameters)

    hbox = gtk.HBox()
    hbox.pack_start(label, expand=True, fill=True, padding=constants.GRID_SIZE)
    hbox.pack_start(close_button, expand=False, fill=False, padding=0)

    event_box = gtk.EventBox()
    event_box.set_name("tab_label")  # required for gtkrc
    event_box.connect('button-press-event', handle_click, *additional_parameters)
    event_box.tab_label = label
    event_box.add(hbox)
    event_box.show_all()

    return event_box, label


def set_tab_label_texts(label, state_machine_m, unsaved_changes=False):
    state_machine_id = state_machine_m.state_machine.state_machine_id
    root_state_name = state_machine_m.root_state.state.name
    root_state_name_trimmed = text_formatting.limit_string(root_state_name, ROOT_STATE_NAME_MAX_CHARS)
    state_machine_path = state_machine_m.state_machine.file_system_path or "[not yet saved]"
    label_text = "{0}&#8201;&#8226;&#8201;{1}".format(state_machine_id, root_state_name_trimmed)
    tooltip_text = root_state_name + "\n\nPath: " + state_machine_path
    if unsaved_changes:
        label_text += '&#8201;*'
    label.set_markup(label_text)
    label.set_tooltip_text(tooltip_text)


def add_state_machine(widget, event=None):
    """Create a new state-machine when the user clicks on the '+' next to the tabs"""
    logger.debug("Creating new state-machine...")
    root_state = HierarchyState("new root state")
    state_machine = StateMachine(root_state)
    rafcon.core.singleton.state_machine_manager.add_state_machine(state_machine)


class StateMachinesEditorController(ExtendedController):
    """Controller handling the State Machines Editor

    :param  rafcon.gui.models.state_machine_manager.StateMachineManagerModel sm_manager_model: The state machine manager
         model, holding data regarding state machines.
    :param rafcon.gui.views.state_machines_editor.StateMachinesEditorView view: The GTK view showing the tabs of state
        machines.
    """
    # TODO the state machine manger controller needs to to adapt the labels according file_system_path changes (observe)
    def __init__(self, state_machine_manager_model, view):
        assert isinstance(state_machine_manager_model, StateMachineManagerModel)
        assert isinstance(view, StateMachinesEditorView)
        ExtendedController.__init__(self, state_machine_manager_model, view, spurious=True)

        self.tabs = {}
        self.last_focused_state_machine_ids = collections.deque(maxlen=10)

    def register_view(self, view):
        """Called when the View was registered"""
        super(StateMachinesEditorController, self).register_view(view)
        self.view['notebook'].connect("add_clicked", add_state_machine)
        self.view['notebook'].connect('switch-page', self.on_switch_page)

        # Add all already open state machines
        for state_machine in self.model.state_machines.itervalues():
            self.add_graphical_state_machine_editor(state_machine)

    def register_actions(self, shortcut_manager):
        """Register callback methods fot triggered actions.

        :param rafcon.gui.shortcut_manager.ShortcutManager shortcut_manager: Shortcut Manager Object holding mappings
            between shortcuts and actions.
        """
        shortcut_manager.add_callback_for_action('close', self.on_close_shortcut)

        # Call register_action of parent in order to register actions for child controllers
        super(StateMachinesEditorController, self).register_actions(shortcut_manager)

    def close_state_machine(self, widget, page_number, event=None):
        """Triggered when the close button in the tab is clicked
        """
        page = widget.get_nth_page(page_number)
        for tab_info in self.tabs.itervalues():
            if tab_info['page'] is page:
                state_machine_m = tab_info['state_machine_m']
                self.on_close_clicked(event, state_machine_m, None, force=False)
                return

    def on_close_shortcut(self, *args):
        """Close selected state machine (triggered by shortcut)"""
        state_machine_m = self.model.get_selected_state_machine_model()
        if state_machine_m is None:
            return
        self.on_close_clicked(None, state_machine_m, None, force=False)

    def on_switch_page(self, notebook, page_pointer, page_num):
        # Important: The method notification_selected_sm_changed will trigger this method, which in turn will trigger
        #               the notification_selected_sm_changed method again, thus some parts of this function will be
        #               triggered twice => take care
        # From documentation: Note the page parameter is a GPointer and not usable within PyGTK. Use the page_num
        # parameter to retrieve the new current page using the get_nth_page() method.
        page = notebook.get_nth_page(page_num)
        for tab_info in self.tabs.itervalues():
            if tab_info['page'] is page and tab_info['state_machine_m'].state_machine:
                new_sm_id = tab_info['state_machine_m'].state_machine.state_machine_id
                if self.model.selected_state_machine_id != new_sm_id:
                    self.model.selected_state_machine_id = new_sm_id
                if self.last_focused_state_machine_ids and \
                        self.last_focused_state_machine_ids[len(self.last_focused_state_machine_ids) - 1] != new_sm_id:
                    self.last_focused_state_machine_ids.append(new_sm_id)
                return page

    def rearrange_state_machines(self, page_num_by_sm_id):
        for sm_id, page_num in page_num_by_sm_id.iteritems():
            state_machine_m = self.tabs[sm_id]['state_machine_m']
            tab, tab_label = create_tab_header('', self.on_close_clicked, self.on_mouse_right_click,
                                               state_machine_m, 'refused')
            set_tab_label_texts(tab_label, state_machine_m, state_machine_m.state_machine.marked_dirty)
            page = self.tabs[sm_id]['page']
            self.view.notebook.remove_page(self.get_page_num(sm_id))
            self.view.notebook.insert_page(page, tab, page_num)

    def get_page_num(self, state_machine_id):
        page = self.tabs[state_machine_id]['page']
        page_num = self.view.notebook.page_num(page)
        return page_num

    def get_page_for_state_machine_id(self, state_machine_id):
        return self.tabs[state_machine_id]['page']

    def get_state_machine_id_for_page(self, page):
        for tab_info in self.tabs.itervalues():
            if tab_info['page'] is page:
                return tab_info['state_machine_m'].state_machine.state_machine_id

    def add_graphical_state_machine_editor(self, state_machine_m):
        """Add to for new state machine

        If a new state machine was added, a new tab is created with a graphical editor for this state machine.

        :param StateMachineModel state_machine_m: The new state machine model
        """
        assert isinstance(state_machine_m, StateMachineModel)

        sm_id = state_machine_m.state_machine.state_machine_id
        logger.debug("Create new graphical editor for state machine with id %s" % str(sm_id))

        if global_gui_config.get_config_value('GAPHAS_EDITOR', False) and GAPHAS_AVAILABLE or not GL_ENABLED:
            if not GL_ENABLED and not global_gui_config.get_config_value('GAPHAS_EDITOR', False):
                logger.info("Gaphas editor is used. "
                            "The gui-config is set to use OpenGL editor but not all libraries needed are provided.")
            graphical_editor_view = GraphicalEditorGaphasView(state_machine_m)
            graphical_editor_ctrl = GraphicalEditorGaphasController(state_machine_m, graphical_editor_view)
        else:
            graphical_editor_view = GraphicalEditorView()
            graphical_editor_ctrl = GraphicalEditorController(state_machine_m, graphical_editor_view)

        self.add_controller(sm_id, graphical_editor_ctrl)

        tab, tab_label = create_tab_header('', self.on_close_clicked, self.on_mouse_right_click,
                                           state_machine_m, 'refused')
        set_tab_label_texts(tab_label, state_machine_m, state_machine_m.state_machine.marked_dirty)

        page = graphical_editor_view['main_frame']

        self.view.notebook.append_page(page, tab)
        self.view.notebook.set_tab_reorderable(page, True)
        page.show_all()

        self.tabs[sm_id] = {'page': page,
                            'state_machine_m': state_machine_m,
                            'file_system_path': state_machine_m.state_machine.file_system_path,
                            'marked_dirty': state_machine_m.state_machine.marked_dirty,
                            'root_state_name': state_machine_m.state_machine.root_state.name}

        self.observe_model(state_machine_m)
        graphical_editor_view.show()
        self.view.notebook.show()
        self.last_focused_state_machine_ids.append(sm_id)

    @ExtendedController.observe("selected_state_machine_id", assign=True)
    def notification_selected_sm_changed(self, model, prop_name, info):
        """If a new state machine is selected, make sure the tab is open"""
        selected_state_machine_id = self.model.selected_state_machine_id
        if selected_state_machine_id is None:
            return

        page_id = self.get_page_num(selected_state_machine_id)

        # to retrieve the current tab colors
        number_of_pages = self.view["notebook"].get_n_pages()
        old_label_colors = range(number_of_pages)
        for p in range(number_of_pages):
            page = self.view["notebook"].get_nth_page(p)
            label = self.view["notebook"].get_tab_label(page).get_child().get_children()[0]
            old_label_colors[p] = label.get_style().fg[gtk.STATE_NORMAL]

        if not self.view.notebook.get_current_page() == page_id:
            self.view.notebook.set_current_page(page_id)

        # set the old colors
        for p in range(number_of_pages):
            page = self.view["notebook"].get_nth_page(p)
            label = self.view["notebook"].get_tab_label(page).get_child().get_children()[0]
            label.modify_fg(gtk.STATE_ACTIVE, old_label_colors[p])
            label.modify_fg(gtk.STATE_INSENSITIVE, old_label_colors[p])

    def set_active_state_machine(self, state_machine_id):
        page_num = self.get_page_num(state_machine_id)
        self.view.notebook.set_current_page(page_num)

    @ExtendedController.observe("state_machines", after=True)
    def model_changed(self, model, prop_name, info):
        # Check for new state machines
        for sm_id, sm in self.model.state_machine_manager.state_machines.iteritems():
            if sm_id not in self.tabs:
                self.add_graphical_state_machine_editor(self.model.state_machines[sm_id])

        # Check for removed state machines
        state_machines_to_be_deleted = []
        for sm_id in self.tabs:
            if sm_id not in self.model.state_machine_manager.state_machines:
                state_machines_to_be_deleted.append(self.tabs[sm_id]['state_machine_m'])
        for state_machine_m in state_machines_to_be_deleted:
            self.remove_state_machine_tab(state_machine_m)

    @ExtendedController.observe("state_machine", after=True)
    def change_in_state_machine_data(self, model, prop_name, info):
        root_state_name_changed = 'root_state_change' == info['method_name'] and 'state' == info['kwargs']['prop_name'] \
                                  and 'name' == info['kwargs']['method_name']
        if info['method_name'] in ['file_system_path', 'marked_dirty'] or root_state_name_changed:
            self.update_state_machine_tab_label(model)

    def update_state_machine_tab_label(self, state_machine_m):
        """ Updates tab label if needed because system path, root state name or marked_dirty flag changed

        :param StateMachineModel state_machine_m: State machine model that has changed
        :return:
        """
        sm_id = state_machine_m.state_machine.state_machine_id
        if sm_id in self.tabs:
            sm = state_machine_m.state_machine
            # create new tab label if tab label properties are not up to date
            if not self.tabs[sm_id]['marked_dirty'] == sm.marked_dirty or \
                    not self.tabs[sm_id]['file_system_path'] == sm.file_system_path or \
                    not self.tabs[sm_id]['root_state_name'] == sm.root_state.name:

                label = self.view["notebook"].get_tab_label(self.tabs[sm_id]["page"]).get_child().get_children()[0]
                set_tab_label_texts(label, state_machine_m, unsaved_changes=sm.marked_dirty)

                self.tabs[sm_id]['file_system_path'] = sm.file_system_path
                self.tabs[sm_id]['marked_dirty'] = sm.marked_dirty
                self.tabs[sm_id]['root_state_name'] = sm.root_state.name
        else:
            logger.warning("State machine '{0}' tab label can not be updated there is no tab.".format(sm_id))

    def on_mouse_right_click(self, event, state_machine_m, result):

        menu = gtk.Menu()
        for sm_id, sm_m in self.model.state_machines.iteritems():
            menu_item = create_image_menu_item(sm_m.root_state.state.name, constants.BUTTON_EXCHANGE,
                                               callback=self.change_selected_state_machine_id, callback_args=[sm_id])
            menu.append(menu_item)

        menu_item = create_image_menu_item("New State Machine", constants.BUTTON_ADD,
                                           callback=add_state_machine, callback_args=[])
        menu.append(menu_item)

        if self.model.state_machines:
            menu_item = create_image_menu_item("Close State Machine", constants.BUTTON_CLOSE,
                                               callback=self.on_close_clicked,
                                               callback_args=[state_machine_m, None])
            menu.append(menu_item)

        menu.show_all()
        menu.popup(None, None, None, event.button, event.time)
        return True

    def change_selected_state_machine_id(self, widget, new_selected_state_machine_id):
        self.model.selected_state_machine_id = new_selected_state_machine_id

    def on_close_clicked(self, event, state_machine_m, result, force=False):
        """Triggered when the close button of a state machine tab is clicked

        Closes state machine if it is saved. Otherwise gives the user the option to 'Close without Saving' or to 'Cancel
        the Close Operation'

        :param state_machine_m: The selected state machine model.
        """
        from rafcon.core.singleton import state_machine_execution_engine, state_machine_manager
        force = True if event is not None and hasattr(event, 'state') and \
                        event.state & SHIFT_MASK and event.state & CONTROL_MASK else force

        def remove_state_machine_m():
            state_machine_id = state_machine_m.state_machine.state_machine_id
            if state_machine_id in self.model.state_machine_manager.state_machines:
                self.model.state_machine_manager.remove_state_machine(state_machine_id)

        def push_sm_running_dialog():

            message_string = "The state machine is still running. Are you sure you want to close?"
            dialog = RAFCONButtonDialog(message_string, ["Stop and close", "Cancel"],
                                        message_type=gtk.MESSAGE_QUESTION, parent=self.get_root_window())
            response_id = dialog.run()
            dialog.destroy()
            if response_id == 1:
                logger.debug("State machine execution is being stopped")
                state_machine_execution_engine.stop()
                remove_state_machine_m()
                return True
            elif response_id == 2:
                logger.debug("State machine execution will keep running")
            return False

        def push_sm_dirty_dialog():

            sm_id = state_machine_m.state_machine.state_machine_id
            root_state_name = state_machine_m.root_state.state.name
            message_string = "There are unsaved changed in the state machine '{0}' with id {1}. Do you want to close " \
                             "the state machine anyway?".format(root_state_name, sm_id)
            dialog = RAFCONButtonDialog(message_string, ["Close without saving", "Cancel"],
                                        message_type=gtk.MESSAGE_QUESTION, parent=self.get_root_window())
            response_id = dialog.run()
            dialog.destroy()
            if response_id == 1:  # Close without saving pressed
                remove_state_machine_m()
                return True
            else:
                logger.debug("Closing of state machine model canceled")
            return False

        # sm running
        if not state_machine_execution_engine.finished_or_stopped() and \
                state_machine_manager.active_state_machine_id == state_machine_m.state_machine.state_machine_id:
            return push_sm_running_dialog()
        # close is forced -> sm not saved
        elif force:
            remove_state_machine_m()
            return True
        # sm dirty -> save sm request dialog
        elif state_machine_m.state_machine.marked_dirty:
            return push_sm_dirty_dialog()
        else:
            remove_state_machine_m()
            return True

    def remove_state_machine_tab(self, state_machine_m):
        """

        :param state_machine_m: The selected state machine model.
        """
        sm_id = state_machine_m.state_machine_id
        self.relieve_model(state_machine_m)

        copy_of_last_opened_state_machines = copy.deepcopy(self.last_focused_state_machine_ids)

        # the following statement will switch the selected notebook tab automatically and the history of the
        # last opened state machines will be destroyed

        # Removing the controller causes the tab to be closed
        self.remove_controller(sm_id)

        del self.tabs[sm_id]
        self.last_focused_state_machine_ids = copy_of_last_opened_state_machines

        # Open tab with next state machine
        sm_keys = self.model.state_machine_manager.state_machines.keys()

        if len(sm_keys) > 0:
            sm_id = -1
            while sm_id not in sm_keys:
                if len(self.last_focused_state_machine_ids) > 0:
                    sm_id = self.last_focused_state_machine_ids.pop()
                else:
                    sm_id = self.model.state_machine_manager.state_machines[sm_keys[0]].state_machine_id

            self.model.selected_state_machine_id = sm_id
        else:
            self.model.selected_state_machine_id = None

    def close_all_pages(self):
        """Closes all tabs of the state machines editor."""
        state_machine_m_list = [tab['state_machine_m'] for tab in self.tabs.itervalues()]
        for state_machine_m in state_machine_m_list:
            self.on_close_clicked(None, state_machine_m, None, force=True)

    def highlight_execution_of_currently_active_sm(self, active):
        """
        High light active state machine. Please consider the difference between active and selected state machine.
        :param active: a flag if the state machine has to be shown as running
        :return:
        """

        notebook = self.view['notebook']
        active_state_machine_id = self.model.state_machine_manager.active_state_machine_id
        if active_state_machine_id is None:
            return
        else:
            page = self.get_page_for_state_machine_id(active_state_machine_id)
            if page is None:
                # logger.warning("No state machine open {0}".format(page_num))
                return

        label = notebook.get_tab_label(page).get_child().get_children()[0]
        if active:
            draw_for_all_gtk_states(label,
                                    "modify_fg",
                                    gtk.gdk.color_parse(global_gui_config.colors['STATE_MACHINE_ACTIVE']))
        else:
            draw_for_all_gtk_states(label,
                                    "modify_fg",
                                    gtk.gdk.color_parse(global_gui_config.colors['STATE_MACHINE_NOT_ACTIVE']))

    def refresh_state_machines(self, state_machine_ids):
        """ Refresh list af state machine tabs

        :param list state_machine_ids: List of state machine ids to be refreshed
        :return:
        """
        # remember current selected state machine id
        currently_selected_sm_id = None
        if self.model.get_selected_state_machine_model():
            currently_selected_sm_id = self.model.get_selected_state_machine_model().state_machine.state_machine_id

        # create a dictionary from state machine id to state machine path and one for tab page number for recovery
        state_machine_path_by_sm_id = {}
        page_num_by_sm_id = {}
        for sm_id, sm in self.model.state_machine_manager.state_machines.iteritems():
            # the sm.base_path is only None if the state machine has never been loaded or saved before
            if sm_id in state_machine_ids and sm.file_system_path is not None:
                state_machine_path_by_sm_id[sm_id] = sm.file_system_path
                page_num_by_sm_id[sm_id] = self.get_page_num(sm_id)

        # close all state machine in list and remember if one was not closed
        for sm_id in state_machine_ids:
            was_closed = self.on_close_clicked(None, self.model.state_machines[sm_id], None, force=True)
            if not was_closed and sm_id in page_num_by_sm_id:
                logger.info("State machine with id {0} will not be re-open because was not closed.".format(sm_id))
                del state_machine_path_by_sm_id[sm_id]
                del page_num_by_sm_id[sm_id]

        # reload state machines from file system
        try:
            self.model.state_machine_manager.open_state_machines(state_machine_path_by_sm_id)
        except AttributeError as e:
            logger.warning("Not all state machines were re-open because {0}".format(e))
        import rafcon.gui.utils
        rafcon.gui.utils.wait_for_gui()  # TODO check again this is needed  to secure that all sm-models are generated

        # recover tab arrangement
        self.rearrange_state_machines(page_num_by_sm_id)

        # recover initial selected state machine and case handling if now state machine is open anymore
        if currently_selected_sm_id:
            # case if only unsaved state machines are open
            if currently_selected_sm_id in self.model.state_machine_manager.state_machines.iterkeys():
                self.set_active_state_machine(currently_selected_sm_id)

    def refresh_state_machine_by_id(self, state_machine_id):
        """ Refreshes only a specific state machine id

        :param int state_machine_id: State machine id of state machine that should be refreshed
        """
        self.refresh_state_machines([state_machine_id])

    def refresh_all_state_machines(self):
        """ Refreshes all state machine tabs
        """
        self.refresh_state_machines(self.model.state_machine_manager.state_machines.keys())
