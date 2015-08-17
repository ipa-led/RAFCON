"""
.. module:: enums
   :platform: Unix, Windows
   :synopsis: A module which holds all global enumerations for the state machine

.. moduleauthor:: Sebastian Brunner


"""

from enum import Enum

DataPortType = Enum('DATA_PORT_TYPE', 'INPUT OUTPUT SCOPED')
StateType = Enum('STATE_TYPE', 'EXECUTION HIERARCHY BARRIER_CONCURRENCY PREEMPTION_CONCURRENCY LIBRARY DECIDER_STATE')
MethodName = Enum('METHOD_NAME', 'EXECUTE CALL_CONTAINER_STATE')
StateExecutionState = Enum('STATE_EXECUTION_STATE', 'INACTIVE ACTIVE EXECUTE_CHILDREN WAIT_FOR_NEXT_STATE')
StateMachineExecutionStatus = Enum('STATE_MACHINE_EXECUTION_STATUS', 'STARTED STOPPED PAUSED STEP BACKWARD_STEP')

# Constants
UNIQUE_DECIDER_STATE_ID = "unique_decider_state_id"
DEFAULT_SCRIPT_PATH = "/tmp/DFC/"