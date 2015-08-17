from gaphas.tool import Tool, ItemTool, HoverTool, HandleTool, RubberbandTool
from gaphas.aspect import Connector, HandleFinder, ItemConnectionSink
from gaphas.item import NW

from rafcon.mvc.views.gap.connection import ConnectionView, ConnectionPlaceholderView, TransitionView,\
    DataFlowView, FromScopedVariableDataFlowView, ToScopedVariableDataFlowView
from rafcon.mvc.views.gap.ports import IncomeView, OutcomeView, InputPortView, OutputPortView, \
    ScopedVariablePortView
from rafcon.mvc.views.gap.state import StateView, NameView

from rafcon.mvc.controllers.gap.aspect import HandleInMotion
from rafcon.mvc.controllers.gap import gap_helper
from rafcon.mvc.singleton import state_machine_manager_model

import gtk
from gtk.gdk import CONTROL_MASK
from enum import Enum
from math import pow

from rafcon.mvc.statemachine_helper import StateMachineHelper

from rafcon.utils import log
logger = log.get_logger(__name__)


PortMoved = Enum('PORT', 'FROM TO')


class RemoveItemTool(Tool):
    """
    This tool is responsible of deleting the selected item
    """

    def __init__(self, graphical_editor_view, view=None):
        super(RemoveItemTool, self).__init__(view)
        self._graphical_editor_view = graphical_editor_view

    def on_key_release(self, event):
        if gtk.gdk.keyval_name(event.keyval) == "Delete":
            # Delete Transition from state machine
            if isinstance(self.view.focused_item, TransitionView):
                StateMachineHelper.delete_model(self.view.focused_item.model)
                return True
            # Delete DataFlow from state machine
            if isinstance(self.view.focused_item, DataFlowView):
                StateMachineHelper.delete_model(self.view.focused_item.model)
                return True
            # Delete selected state(s) from state machine
            if isinstance(self.view.focused_item, StateView):
                if self.view.has_focus():
                    self._graphical_editor_view.emit('remove_state_from_state_machine')
                    return True


class MoveItemTool(ItemTool):
    """
    This class is responsible of moving states, names, connections, etc.
    """

    def __init__(self, graphical_editor_view, view=None, buttons=(1,)):
        super(MoveItemTool, self).__init__(view, buttons)
        self._graphical_editor_view = graphical_editor_view

        self._item = None

    def on_button_press(self, event):
        super(MoveItemTool, self).on_button_press(event)

        item = self.get_item()
        if isinstance(item, StateView):
            self._item = item

        if (isinstance(self.view.focused_item, NameView) and not
                state_machine_manager_model.get_selected_state_machine_model().selection.is_selected(
                    self.view.focused_item.parent.model)):
            self.view.focused_item = self.view.focused_item.parent
            self._item = self.view.focused_item

        if not self.view.is_focus():
            self.view.grab_focus()
        if isinstance(self.view.focused_item, StateView):
            self._graphical_editor_view.emit('new_state_selection', self.view.focused_item)

        if event.button == 3:
            self._graphical_editor_view.emit('deselect_states')

        return True

    def on_button_release(self, event):
        if isinstance(self._item, StateView):
            self._item.moving = False
            self.view.canvas.request_update(self._item)
            self._graphical_editor_view.emit('meta_data_changed', self._item.model, "Move state", True)

            self._item = None

            self.view.redraw_complete_screen()

        if isinstance(self.view.focused_item, NameView):
            self._graphical_editor_view.emit('meta_data_changed', self.view.focused_item.parent.model, "Move name", False)

        return super(MoveItemTool, self).on_button_release(event)

    def on_motion_notify(self, event):
        """
        Normally do nothing.
        If a button is pressed move the items around.
        """
        if event.state & gtk.gdk.BUTTON_PRESS_MASK:

            if self._item and not self._item.moving:
                self._item.moving = True

            if not self._movable_items:
                # Start moving
                self._movable_items = set(self.movable_items())
                for inmotion in self._movable_items:
                    inmotion.start_move((event.x, event.y))

            for inmotion in self._movable_items:
                inmotion.move((event.x, event.y))
                rel_pos = gap_helper.calc_rel_pos_to_parent(self.view.canvas, inmotion.item, inmotion.item.handles()[NW])
                if isinstance(inmotion.item, StateView):
                    state_m = inmotion.item.model
                    state_m.meta['gui']['editor_gaphas']['rel_pos'] = rel_pos
                    state_m.meta['gui']['editor_opengl']['rel_pos'] = (rel_pos[0], -rel_pos[1])
                elif isinstance(inmotion.item, NameView):
                    state_m = self.view.canvas.get_parent(inmotion.item).model
                    state_m.meta['name']['gui']['editor_gaphas']['rel_pos'] = rel_pos
                    state_m.meta['name']['gui']['editor_opengl']['rel_pos'] = (rel_pos[0], -rel_pos[1])

            return True


class HoverItemTool(HoverTool):

    def __init__(self, view=None):
        super(HoverItemTool, self).__init__(view)
        self._prev_hovered_item = None

    def on_motion_notify(self, event):
        super(HoverItemTool, self).on_motion_notify(event)

        if self._prev_hovered_item and self.view.hovered_item is not self._prev_hovered_item:
            self._prev_hovered_item.hovered = False
        if isinstance(self.view.hovered_item, StateView):
            self.view.hovered_item.hovered = True
            self._prev_hovered_item = self.view.hovered_item


class MultiselectionTool(RubberbandTool):

    def __init__(self, graphical_editor_view, view=None):
        super(MultiselectionTool, self).__init__(view)

        self._graphical_editor_view = graphical_editor_view

    def on_button_press(self, event):
        if event.state & gtk.gdk.CONTROL_MASK and event.state & gtk.gdk.SHIFT_MASK:
            return super(MultiselectionTool, self).on_button_press(event)
        return False

    def on_motion_notify(self, event):
        if event.state & gtk.gdk.BUTTON_PRESS_MASK and event.state & gtk.gdk.CONTROL_MASK and \
                event.state & gtk.gdk.SHIFT_MASK:
            view = self.view
            self.queue_draw(view)
            self.x1, self.y1 = event.x, event.y
            self.queue_draw(view)
            return True

    def on_button_release(self, event):
        self.queue_draw(self.view)
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        # Hold down ALT-key to add selection to current selection
        if event.state & gtk.gdk.MOD1_MASK:
            items_to_deselect = []
        else:
            items_to_deselect = list(self.view.selected_items)
        self.view.select_in_rectangle((min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))

        for item in self.view.selected_items:
            if not isinstance(item, StateView):
                items_to_deselect.append(item)

        for item in items_to_deselect:
            if item in self.view.selected_items:
                self.view.unselect_item(item)

        self._graphical_editor_view.emit('new_state_selection', self.view.selected_items)

        return True


class HandleMoveTool(HandleTool):

    def __init__(self, graphical_editor_view, view=None):
        super(HandleMoveTool, self).__init__(view)

        self._graphical_editor_view = graphical_editor_view

        self._child_resize = False

        self._last_active_port = None
        self._new_connection = None

        self._start_state = None
        self._start_width = None
        self._start_height = None

        self._last_hovered_state = None
        self._glue_distance = .5

        self._active_connection_view = None
        self._active_connection_view_handle = None
        self._start_port = None  # Port where connection view pull starts
        self._check_port = None  # Port of connection view that is not pulled

        self._waypoint_list = None

    def on_button_press(self, event):
        view = self.view
        item, handle = HandleFinder(view.hovered_item, view).get_handle_at_point((event.x, event.y))

        if isinstance(item, ConnectionView):
            # If moved handles item is a connection save all necessary information (where did the handle start,
            # what is the connections other end)
            if handle is item.handles()[1] or handle is item.handles()[len(item.handles()) - 2]:
                return False
            self._active_connection_view = item
            self._active_connection_view_handle = handle
            if handle is item.from_handle():
                self._start_port = item.from_port
                self._check_port = item.to_port
            elif handle is item.to_handle():
                self._start_port = item.to_port
                self._check_port = item.from_port

        if isinstance(item, TransitionView):
            self._waypoint_list = item.model.meta['gui']['editor_gaphas']['waypoints']

        # Set start state
        if isinstance(item, StateView):
            self._start_state = item
            self._start_width = item.width
            self._start_height = item.height

        if handle:
            # Deselect all items unless CTRL or SHIFT is pressed
            # or the item is already selected.
            if not (event.state & (gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK)
                    or view.hovered_item in view.selected_items):
                del view.selected_items

            view.hovered_item = item
            view.focused_item = item

            self.motion_handle = None

            self.grab_handle(item, handle)

            return True

    def _get_drop_item(self, pos):
        """
        Find state the new connection was dropped on. Returns the state if valid connection found, None otherwise.
        Invalid connections are: state connection to itself, connection across hierarchy levels.
        :param pos: Position to check for drop_item
        :return: State connection was dropped on or None
        """
        get_parent = self.view.canvas.get_parent
        drop_item = self.view.get_item_at_point_exclude(pos, exclude=[self._new_connection])
        if drop_item and not isinstance(drop_item, StateView):
            drop_item = get_parent(drop_item)
        parent = self._start_state

        if (isinstance(self._new_connection.from_port, IncomeView) and
                drop_item not in self.view.canvas.get_children(parent)):
            drop_item = None
        elif (isinstance(self._new_connection.from_port, OutcomeView) and
              drop_item not in self.view.canvas.get_children(get_parent(parent))):
            drop_item = None

        if drop_item:
            assert isinstance(drop_item, StateView)

        return drop_item

    def on_button_release(self, event):
        # Create new transition if pull beginning at port occurred
        if self._new_connection:
            drop_item = self._get_drop_item((event.x, event.y))
            gap_helper.create_new_connection(self._start_state,
                                             self._new_connection.from_port,
                                             self._new_connection.to_port,
                                             drop_state=drop_item)

            # remove placeholder from canvas
            self._new_connection.remove_connection_from_ports()
            self.view.canvas.remove(self._new_connection)

        # if connection has been pulled to another port, update port
        if self._last_active_port is not self._start_port:
            item = self._active_connection_view
            handle = self._active_connection_view_handle
            if isinstance(item, TransitionView) and handle in item.end_handles():
                self._handle_transition_view_change(item, handle)
            elif isinstance(item, DataFlowView) and handle in item.end_handles():
                self._handle_data_flow_view_change(item, handle)
        # if connection has been put back to original position, reset port
        elif (self._last_active_port is self._start_port and self._active_connection_view and
                self._active_connection_view_handle in self._active_connection_view.end_handles()):
            item = self._active_connection_view
            handle = self._active_connection_view_handle
            self._handle_reset_ports(item, handle, self._start_port.parent)

        if isinstance(self._active_connection_view, TransitionView):
            gap_helper.update_transition_waypoints(self._graphical_editor_view, self._active_connection_view, self._waypoint_list)

        if isinstance(self.grabbed_item, (StateView, NameView)):

            if self._child_resize and isinstance(self.grabbed_item, StateView):

                def update_meta_data(state):
                    for transition_v in state.get_transitions():
                        gap_helper.update_transition_waypoints(self._graphical_editor_view, transition_v, None)
                    gap_helper.update_meta_data_for_item(self._graphical_editor_view, self.grabbed_handle, state, True)
                    for child_state_v in state.child_state_vs:
                        update_meta_data(child_state_v)

                update_meta_data(self.grabbed_item)
                self._child_resize = False
            gap_helper.update_meta_data_for_item(self._graphical_editor_view, self.grabbed_handle, self.grabbed_item)

        # reset temp variables
        self._last_active_port = None
        self._check_port = None
        self._new_connection = None
        self._start_state = None
        self._start_width = None
        self._start_height = None
        self._active_connection_view = None
        self._active_connection_view_handle = None
        self._waypoint_list = None
        self._glue_distance = 0
        self._last_hovered_state = None

        super(HandleMoveTool, self).on_button_release(event)

    def on_motion_notify(self, event):
        """
        Handle motion events. If a handle is grabbed: drag it around,
        else, if the pointer is over a handle, make the owning item the
        hovered-item.
        """
        view = self.view
        # If no new transition exists and the grabbed handle is a port handle a new placeholder connection is
        # inserted into canvas
        # This is the default case if one starts to pull from a port handle
        if (not self._new_connection and self.grabbed_handle and event.state & gtk.gdk.BUTTON_PRESS_MASK and
                isinstance(self.grabbed_item, StateView) and not event.state & gtk.gdk.CONTROL_MASK):
            canvas = view.canvas
            # start_state = self.grabbed_item
            start_state = self._start_state
            start_state_parent = canvas.get_parent(start_state)

            handle = self.grabbed_handle
            start_port = gap_helper.get_port_for_handle(handle, start_state)

            # If the start state has a parent continue (ensure no transition is created from top level state)
            if (start_port and (isinstance(start_state_parent, StateView) or
                                (start_state_parent is None and isinstance(start_port, (IncomeView, InputPortView,
                                                                                        ScopedVariablePortView))))):

                # Go up one hierarchy_level to match the transitions line width
                transition_placeholder = isinstance(start_port, IncomeView) or isinstance(start_port, OutcomeView)
                placeholder_v = ConnectionPlaceholderView(max(start_state.hierarchy_level - 1, 1),
                                                          transition_placeholder)
                self._new_connection = placeholder_v

                canvas.add(placeholder_v, start_state_parent)

                # Check for start_port type and adjust hierarchy_level as well as connect the from handle to the
                # start port of the state
                if isinstance(start_port, IncomeView):
                    placeholder_v.hierarchy_level = start_state.hierarchy_level
                    start_state.connect_to_income(placeholder_v, placeholder_v.from_handle())
                elif isinstance(start_port, OutcomeView):
                    start_state.connect_to_outcome(start_port.outcome_id, placeholder_v, placeholder_v.from_handle())
                elif isinstance(start_port, InputPortView):
                    start_state.connect_to_input_port(start_port.port_id, placeholder_v, placeholder_v.from_handle())
                elif isinstance(start_port, OutputPortView):
                    start_state.connect_to_output_port(start_port.port_id, placeholder_v, placeholder_v.from_handle())
                elif isinstance(start_port, ScopedVariablePortView):
                    start_state.connect_to_scoped_variable_port(start_port.port_id, placeholder_v,
                                                                placeholder_v.from_handle())
                # Ungrab start port handle and grab new transition's to handle to move, also set motion handle
                # to just grabbed handle
                self.ungrab_handle()
                self.grab_handle(placeholder_v, placeholder_v.to_handle())
                self._set_motion_handle(event)

        # the grabbed handle is moved according to mouse movement
        if self.grabbed_handle and event.state & gtk.gdk.BUTTON_PRESS_MASK:
            item = self.grabbed_item
            handle = self.grabbed_handle
            pos = event.x, event.y

            if not self.motion_handle:
                self._set_motion_handle(event)

            # If current handle is from_handle of a connection view
            if isinstance(item, ConnectionView) and item.from_handle() is handle:
                self._get_port_side_size_for_hovered_state(pos)
                self.check_sink_item(self.motion_handle.move(pos, self._glue_distance), handle, item)
            # If current handle is to_handle of a connection view
            elif isinstance(item, ConnectionView) and item.to_handle() is handle:
                self._get_port_side_size_for_hovered_state(pos)
                self.check_sink_item(self.motion_handle.move(pos, self._glue_distance), handle, item)
            elif isinstance(item, TransitionView) and handle not in item.end_handles():
                self.motion_handle.move(pos, 0.)
            # If current handle is port or corner of a state view (for ports it only works if CONTROL key is pressed)
            elif isinstance(item, StateView) and handle in item.corner_handles:
                old_size = (item.width, item.height)
                self.motion_handle.move(pos, 0.)
                if event.state & CONTROL_MASK:
                    self._child_resize = True
                    item.resize_all_children(old_size)
            elif isinstance(item, StateView):
                self.motion_handle.move(pos, 0.)
            # All other handles
            else:
                self.motion_handle.move(pos, 5.0)

            return True

    def _get_port_side_size_for_hovered_state(self, pos):
        item_below = self.view.get_item_at_point(pos, False)
        if isinstance(item_below, NameView):
            item_below = self.view.canvas.get_parent(item_below)
        if isinstance(item_below, StateView) and item_below is not self._last_hovered_state:
            self._last_hovered_state = item_below
            self._glue_distance = item_below.port_side_size / 2.

    def _handle_data_flow_view_change(self, item, handle):

        def is_output_port(port):
            return isinstance(port, OutputPortView) or isinstance(port, ScopedVariablePortView)

        def is_input_port(port):
            return isinstance(port, InputPortView) or isinstance(port, ScopedVariablePortView)

        start_parent = self._start_port.parent
        last_parent = None
        if self._last_active_port:
            last_parent = self._last_active_port.parent

        # Connection changed: input-to-input to input-to-input
        if (is_input_port(self._check_port) and
                is_input_port(self._start_port) and
                is_input_port(self._last_active_port)):
            self._handle_data_flow_change(item, start_parent, last_parent, iti_to_iti=True)
        # Connection changed: input-to-input to output-to-input
        elif (is_input_port(self._check_port) and
                is_input_port(self._start_port) and
                is_output_port(self._last_active_port)):
            self._handle_data_flow_change(item, start_parent, last_parent, iti_to_oti=True)
        # Connection changed: output-to-input to input-to-input
        elif (is_input_port(self._check_port) and
                is_output_port(self._start_port) and
                is_input_port(self._last_active_port)):
            self._handle_data_flow_change(item, start_parent, last_parent, oti_to_iti=True)
        # Connection changed: output-to-input to output-to-input
        elif ((is_output_port(self._check_port) and
                    is_input_port(self._start_port) and
                    is_input_port(self._last_active_port)) or
                (is_input_port(self._check_port) and
                    is_output_port(self._start_port) and
                    is_output_port(self._last_active_port))):
            self._handle_data_flow_change(item, start_parent, last_parent, oti_to_oti=True)
        # Connection changed: output-to-input to output-to-output
        elif (is_output_port(self._check_port) and
                is_input_port(self._start_port) and
                is_output_port(self._last_active_port)):
            self._handle_data_flow_change(item, start_parent, last_parent, oti_to_oto=True)
        # Connection changed: output-to-output to output-to-input
        elif (is_output_port(self._check_port) and
                is_output_port(self._start_port) and
                is_input_port(self._last_active_port)):
            self._handle_data_flow_change(item, start_parent, last_parent, oto_to_oti=True)
        # Connection changed: output-to-output to output-to-output
        elif (is_output_port(self._check_port) and
                is_output_port(self._start_port) and
                is_output_port(self._last_active_port)):
            self._handle_data_flow_change(item, start_parent, last_parent, oto_to_oto=True)
        # Everything else: Reset to original position
        else:
            self._handle_reset_ports(item, handle, start_parent)

    def _handle_transition_view_change(self, item, handle):
        start_parent = self._start_port.parent
        last_parent = None
        if self._last_active_port:
            last_parent = self._last_active_port.parent

        # Connection changed: outcome-to-outcome to outcome-to-outcome
        if (isinstance(self._check_port, OutcomeView) and
                isinstance(self._start_port, OutcomeView) and
                isinstance(self._last_active_port, OutcomeView)):
            self._handle_transition_change(item, start_parent, last_parent, oto_to_oto=True)
        # Connection changed: outcome-to-outcome to outcome-to-income
        elif (isinstance(self._check_port, OutcomeView) and
                isinstance(self._start_port, OutcomeView) and
                isinstance(self._last_active_port, IncomeView)):
            self._handle_transition_change(item, start_parent, last_parent, oto_to_oti=True)
        # Connection changed: outcome-to-income to outcome-to-outcome
        elif (isinstance(self._check_port, OutcomeView) and
                isinstance(self._start_port, IncomeView) and
                isinstance(self._last_active_port, OutcomeView)):
            self._handle_transition_change(item, start_parent, last_parent, oti_to_oto=True)
        # Connection changed: outcome-to-income to outcome-to-income
        elif ((isinstance(self._check_port, IncomeView) and
                    isinstance(self._start_port, OutcomeView) and
                    isinstance(self._last_active_port, OutcomeView)) or
                (isinstance(self._check_port, OutcomeView) and
                    isinstance(self._start_port, IncomeView) and
                    isinstance(self._last_active_port, IncomeView))):
            self._handle_transition_change(item, start_parent, last_parent, oti_to_oti=True)
        # Connection changed: income-to-income to income-to-income (Start State changed)
        elif (isinstance(self._check_port, IncomeView) and
                isinstance(self._start_port, IncomeView) and
                isinstance(self._last_active_port, IncomeView)):
            self._handle_transition_change(item, start_parent, last_parent, iti_to_iti=True)
        else:
            self._handle_reset_ports(item, handle, start_parent)

    def _handle_data_flow_change(self, item, start_parent, last_parent, iti_to_iti=False, iti_to_oti=False,
                                 oti_to_iti=False, oti_to_oti=False, oti_to_oto=False, oto_to_oti=False,
                                 oto_to_oto=False):
        if last_parent is None:
            return
        if not gap_helper.assert_exactly_one_true([iti_to_iti, iti_to_oti, oti_to_iti, oti_to_oti, oti_to_oto,
                                                   oto_to_oti, oto_to_oto]):
            return

        check = self._check_port
        last = self._last_active_port

        port_moved = None
        if check is item.from_port:
            port_moved = PortMoved.TO
        elif check is item.to_port:
            port_moved = PortMoved.FROM

        def reset_handle():
            if port_moved is PortMoved.TO:
                self._handle_reset_ports(item, item.to_handle(), start_parent)
            elif port_moved is PortMoved.FROM:
                self._handle_reset_ports(item, item.from_handle(), start_parent)

        if port_moved is PortMoved.TO:
            # If other port in same parent
            if start_parent is last_parent and (iti_to_iti or oti_to_oti or oto_to_oto):
                item.model.data_flow.to_key = last.port_id
            # If other port not in same parent
            elif start_parent is not last_parent and (iti_to_iti or oti_to_oti or oti_to_oto or oto_to_oti):
                # Check if InputPortView (not at ScopedVariable) is already connected
                if isinstance(last, InputPortView) and last.has_incoming_connection():
                    reset_handle()
                    return
                # Only connect output to output if to_port is in parent of from_port parent
                elif oti_to_oto and last_parent is not self.get_parents_parent_for_port(item.from_port):
                    reset_handle()
                    return
                to_state_id = gap_helper.get_state_id_for_port(last)
                to_key = last.port_id
                item.model.data_flow.modify_target(to_state_id, to_key)
            else:
                reset_handle()
                return
        elif port_moved is PortMoved.FROM:
            # If other port in same parent
            if start_parent is last_parent and (iti_to_iti or oti_to_oti or oto_to_oto):
                item.model.data_flow.from_key = last.port_id
            # If other port not in same parent
            elif start_parent is not last_parent and (iti_to_oti or oti_to_iti or oti_to_oti or oto_to_oto):
                # Prevent to connect input from state in same hierarchy or below
                if oti_to_iti and last_parent is not self.get_parents_parent_for_port(item.to_port):
                    reset_handle()
                    return
                # Prevent to connect output of parent to input of child
                elif oti_to_oti and last_parent is self.get_parents_parent_for_port(item.to_port):
                    reset_handle()
                    return
                # Prevent to connect output with output of same state
                elif oto_to_oto and last_parent is item.to_port.parent:
                    reset_handle()
                    return
                from_state_id = gap_helper.get_state_id_for_port(last)
                from_key = last.port_id
                item.model.data_flow.modify_origin(from_state_id, from_key)
            else:
                reset_handle()
                return

    def _handle_reset_ports(self, connection, handle, start_parent):

        if handle not in connection.handles():
            return

        self.disconnect_last_active_port(handle, connection)
        self.view.canvas.disconnect_item(connection, handle)

        if isinstance(connection, TransitionView):
            start_outcome_id = None
            if isinstance(self._start_port, OutcomeView):
                start_outcome_id = self._start_port.outcome_id

            if start_outcome_id is None:
                start_parent.connect_to_income(connection, handle)
            else:
                start_parent.connect_to_outcome(start_outcome_id, connection, handle)
        elif isinstance(connection, DataFlowView):
            if isinstance(start_parent, StateView):
                if isinstance(self._start_port, InputPortView):
                    start_parent.connect_to_input_port(self._start_port.port_id, connection, handle)
                if isinstance(self._start_port, OutputPortView):
                    start_parent.connect_to_output_port(self._start_port.port_id, connection, handle)
                if isinstance(self._start_port, ScopedVariablePortView):
                    start_parent.connect_to_scoped_variable_port(self._start_port.port_id, connection, handle)

        self.view.canvas.update()

    def get_parents_parent_for_port(self, port):
        """
        Returns the StateView which is the parent of the StateView containing the port. If the ports parent
        is neither of Type StateView nor ScopedVariableView or the parent is the root state, None is returned.
        :param port: Port to return parent's parent
        :return: View containing the parent of the port, None if parent is root state or not of type StateView or ScopedVariableView
        """
        port_parent = port.parent
        if isinstance(port_parent, StateView):
            return self.view.canvas.get_parent(port_parent)
        else:
            return None

    def _handle_transition_change(self, item, start_parent, last_parent, oto_to_oto=False, oto_to_oti=False,
                                  oti_to_oto=False, oti_to_oti=False, iti_to_iti=False):
        """
        This method handles the change of transitions and checks if the new transition is valid.
        Exactly one of the optional parameters need be set to True
        :param item: TransitionView holding the changed transition
        :param start_parent: Parent of start_port
        :param last_parent: Parent of last_active_port
        :param oto_to_oto: Indicates check for 'outcome-to-outcome to outcome-to-outcome' change
        :param oto_to_oti: Indicates check for 'outcome-to-outcome to outcome-to-income' change
        :param oti_to_oto: Indicates check for 'outcome-to-income to outcome-to-outcome' change
        :param oti_to_oti: Indicates check for 'outcome-to-income to outcome-to-income' change
        :param iti_to_iti: Indicates check for 'income-to-income to income-to-income' change
        """
        if last_parent is None:
            return
        if not gap_helper.assert_exactly_one_true([oto_to_oto, oto_to_oti, oti_to_oto, oti_to_oti, iti_to_iti]):
            return

        start_outcome_id = None
        from_outcome_id = None
        last_outcome_id = None

        check = self._check_port
        start = self._start_port
        last = self._last_active_port

        port_moved = None
        if check is item.from_port:
            port_moved = PortMoved.TO
        elif check is item.to_port:
            port_moved = PortMoved.FROM

        if isinstance(start, OutcomeView):
            start_outcome_id = start.outcome_id
        if isinstance(check, OutcomeView):
            from_outcome_id = check.outcome_id
        if isinstance(last, OutcomeView):
            last_outcome_id = last.outcome_id
        state_id = last_parent.model.state.state_id

        if oti_to_oto:
            state_id = start_parent.model.state.state_id
            start_parent = self.view.canvas.get_parent(start_parent)

        # if check_port is from_port then to_port has changed
        if port_moved == PortMoved.TO:
            # if start_port parent is last_active_port parent then connection is still in parent state
            if start_parent is last_parent and (oto_to_oto or oti_to_oto):
                item.model.transition.to_outcome = last_outcome_id
            elif oto_to_oti or oti_to_oto or oti_to_oti or iti_to_iti:
                item.model.transition.to_state = state_id
            # if not in same parent reset transition to initial connection
            else:
                item.model.transition.to_outcome = start_outcome_id
            return
        elif oti_to_oto:
            item.model.transition.from_outcome = from_outcome_id
            return
        elif iti_to_iti:
            self._handle_reset_ports(item, item.from_handle(), start_parent)
            return
        # if check_port is to_port then from_port has changed
        elif port_moved == PortMoved.FROM and (oto_to_oto or oti_to_oti):
            # if start_port parent is last_active_port parent then connection is still in parent state
            if start_parent is last_parent:
                if not last.has_outgoing_connection():
                    item.model.transition.from_outcome = last_outcome_id
                else:
                    item.model.transition.from_outcome = start_outcome_id
                return
            # if not in same parent but other state outcome then modify origin
            else:
                if not last.has_outgoing_connection():
                    if self.is_state_id_root_state(state_id):
                        item.model.transition.from_outcome = start_outcome_id
                    else:
                        item.model.transition.modify_origin(state_id, last_outcome_id)
                    return
                else:
                    item.model.transition.from_outcome = start_outcome_id
                return

    def is_state_id_root_state(self, state_id):
        for state_v in self.view.canvas.get_root_items():
            if state_v.model.state.state_id == state_id:
                return True
        return False

    def _set_motion_handle(self, event):
        """
        Sets motion handle to currently grabbed handle
        """
        item = self.grabbed_item
        handle = self.grabbed_handle
        pos = event.x, event.y
        self.motion_handle = HandleInMotion(item, handle, self.view)
        self.motion_handle.start_move(pos)

    def check_sink_item(self, item, handle, connection):
        """
        Checks if the ConnectionSink's item is a StateView and if so tries for every port (income, outcome, input,
        output) to connect the ConnectionSink's port to the corresponding handle.
        If no matching_port was found or the item is no StateView the last active port is disconnected, as no valid
        connection is currently available for the connection.
        :param item: ItemConnectionSink holding the state and port to connect
        :param handle: Handle to connect port to
        :param connection: Connection containing handle
        """
        if isinstance(item, ItemConnectionSink):
            state = item.item
            if isinstance(state, StateView):
                if (isinstance(connection, TransitionView) or
                        (isinstance(connection, ConnectionPlaceholderView) and connection.transition_placeholder)):
                    if self.set_matching_port(state.get_logic_ports(), item.port, handle, connection):
                        return
                elif isinstance(connection, FromScopedVariableDataFlowView):
                    if handle is connection.from_handle():
                        if self.set_matching_port(state.scoped_variables, item.port, handle, connection):
                            return
                    elif handle is connection.to_handle():
                        if self.set_matching_port(state.inputs, item.port, handle, connection):
                            return
                elif isinstance(connection, ToScopedVariableDataFlowView):
                    if handle is connection.to_handle():
                        if self.set_matching_port(state.scoped_variables, item.port, handle, connection):
                            return
                    elif handle is connection.from_handle():
                        if self.set_matching_port(state.outputs, item.port, handle, connection):
                            return
                elif (isinstance(connection, DataFlowView) or
                        (isinstance(connection, ConnectionPlaceholderView) and not connection.transition_placeholder)):
                    if self.set_matching_port(state.get_data_ports(), item.port, handle, connection):
                        return
        self.disconnect_last_active_port(handle, connection)

    def disconnect_last_active_port(self, handle, connection):
        """
        Disconnects the last active port and updates the connected handles in the port as well as removes the port
        from the connected list in the connection.
        :param handle: Handle to disconnect from
        :param connection: ConnectionView to be disconnected, holding the handle
        """

        if self._last_active_port:
            self._last_active_port.remove_connected_handle(handle)
            self._last_active_port.tmp_disconnect()
            connection.reset_port_for_handle(handle)
            self._last_active_port = None

    def set_matching_port(self, port_list, matching_port, handle, connection):
        """
        Takes a list of PortViews and sets the port matching the matching_port to connected.
        It also updates the ConnectionView's connected port for the given handle and tells the PortView the new
        connected handle.
        If the matching port was found the last active port is disconnected and set to the matching_port
        :param port_list: List of ports to check
        :param matching_port: Port to look for in list
        :param handle: Handle to connect to matching_port
        :param connection: ConnectionView to be connected, holding the handle
        """
        port_to_handle = None

        for port in port_list:
            if port.port is matching_port:
                port_to_handle = port
                break

        if port_to_handle:
            if self._last_active_port is not port_to_handle:
                self.disconnect_last_active_port(handle, connection)
            port_to_handle.add_connected_handle(handle, connection, moving=True)
            port_to_handle.tmp_connect(handle, connection)
            connection.set_port_for_handle(port_to_handle, handle)
            self._last_active_port = port_to_handle
            return True

        return False


class ConnectHandleMoveTool(HandleMoveTool):
    """
    Tool for connecting two items.

    There are two items involved. Handle of connecting item (usually
    a line) is being dragged by an user towards another item (item in
    short). Port of an item is found by the tool and connection is
    established by creating a constraint between line's handle and item's
    port.
    """

    def glue(self, item, handle, vpos):
        """
        Perform a small glue action to ensure the handle is at a proper
        location for connecting.
        """

        # glue_distance is the snapping radius
        if item.from_handle() is handle:
            glue_distance = 1.0 / pow(2, item.hierarchy_level)
        else:
            glue_distance = 1.0 / pow(2, item.hierarchy_level - 1)

        if self.motion_handle:
            return self.motion_handle.glue(vpos, glue_distance)
        else:
            return HandleInMotion(item, handle, self.view).glue(vpos, glue_distance)

    def connect(self, item, handle, vpos):
        """
        Connect a handle of a item to connectable item.

        Connectable item is found by `ConnectHandleTool.glue` method.

        :Parameters:
         item
            Connecting item.
         handle
            Handle of connecting item.
         vpos
            Position to connect to (or near at least)
        """
        connector = Connector(item, handle)

        # find connectable item and its port
        sink = self.glue(item, handle, vpos)

        # no new connectable item, then diconnect and exit
        if sink:
            connector.connect(sink)
        else:
            cinfo = item.canvas.get_connection(handle)
            if cinfo:
                connector.disconnect()

    def on_button_release(self, event):
        item = self.grabbed_item
        handle = self.grabbed_handle
        try:
            if handle and handle.connectable:
                self.connect(item, handle, (event.x, event.y))
        finally:
            return super(ConnectHandleMoveTool, self).on_button_release(event)