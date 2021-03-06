from threading import Thread, Condition, Lock
from AX12 import AX12
import time, json
from typing import Iterable

debug = True

class Action:
    '''
    Represents any action or group of actions a robot can make.
    The actions can be defined as a tree with sequences as nodes and function
    calls as leaves.
    '''
    def __init__(self, callback : callable = lambda : None):
        # callback is called when an action is over
        self.callback = callback
        self.to_be_waited = False
        self.timeout = None
        self.parent_sequence = None
        self.done = False
        # Conditional variable : an object that allows a thread to wait for an event
        # from another thread. Used to wait for actions to end.
        self.done_condvar = Condition()

    def private_callback(self):
        '''
        This function is called when the action is finished.
        '''
        self.done_condvar.acquire()
        self.done = True
        self.done_condvar.notify()
        if not self.callback is None:
            self.callback()
        if not self.parent_sequence is None:
            self.parent_sequence.element_callback()
        self.done_condvar.release()

    def wait(self, timeout : float = None) -> 'Action':
        '''
        Sets the to_be_waited flag: action callbacks will be waited for before
        continuing execution
        '''
        if(self.callback is None):
            raise(Exception("Cannot wait an action without callback"))
        else:
            self.to_be_waited = True
            self.timeout = timeout
        return self

    def exec(self):
        # Private exec is the function that will be executed
        self.private_exec()

        # Handle a blocking call ?
        if(self.to_be_waited):
            self.done_condvar.acquire()
            if not self.done:
                self.done_condvar.wait(self.timeout)
                if not self.done:
                    print(self, "timed out.")
                    self.cancel_exec()
            self.done_condvar.release()

    def private_exec(self):
        #to be overriden
        return None

    def cancel_exec(self):
        if(not (self.callback is None or self.parent_sequence is None)):
            self.parent_sequence.element_cancel()

class Sequence(Action):
    '''
    A sequence is a collection of actions
    '''
    def __init__(self, name : str = None, callback : callable = lambda : None, abort_if_fail : bool = False):
        Action.__init__(self, callback)
        self.action_list = []
        self.current_action_idx = 0
        self.nb_callbacks = 0
        self.name = name
        # A lock preventing a simultaneous construction and execution of the sequence
        self.mutex = Lock()

    def __str__(self) -> str:
        if not self.name is None:
            return "Sequence " + self.name
        else:
            return "Unnamed sequence"

    def add_action(self, action : Action, position : int = -1) -> 'Sequence':
        '''
        Adds an action in the sequence at the given position.
        '''
        self.mutex.acquire()
        position = len(self.action_list) if position == -1 else position
        position = max(self.current_action_idx, position)
        self.action_list.insert(position, action)
        if(not action.callback is None):
            self.nb_callbacks += 1
        action.parent_sequence = self
        self.mutex.release()
        return self

    def add_actions(self, actions) -> 'Sequence':
        '''
        Takes a list of actions and adds it in order to the sequence.
        '''
        for action in actions:
            self.add_action(action)
        return self

    def element_callback(self):
        '''
        Called whenever an action of the sequence executes its callback.
        Allows to count the number of callbacks left.
        '''
        self.mutex.acquire()
        self.nb_callbacks -= 1
        print("Callback received in sequence", self.name, ",", \
                self.nb_callbacks, "expected callbacks left")
        # If all expected callbacks have been received, call the sequence callback
        no_callbacks_left = self.nb_callbacks == 0
        self.mutex.release()
        if no_callbacks_left:
            self.private_callback()


    def element_cancel(self):
        '''
        Called when an element of the sequence cancels its execution, in particular
        in a timeout situation.
        '''
        self.mutex.acquire()
        self.nb_callbacks -= 1
        print("Element execution canceled in sequence", self.name, ",", \
                self.nb_callbacks, "expected callbacks left")
        # If all expected callbacks have been received, call the sequence callback
        no_callbacks_left = self.nb_callbacks == 0
        self.mutex.release()
        if no_callbacks_left:
            self.private_callback()
        #FIXME: abort_if_fail??
        elif abort_if_fail:
            self.cancel_exec()


    def private_exec(self):
        '''
        Is called by the Action.exec() function. Executes the actions of all elements of
        the sequence.
        '''
        while self.current_action_idx < len(self.action_list):
            if debug:
                print("Executing action number", self.current_action_idx, \
                       "in sequence", self.name)
            self.mutex.acquire()
            action = self.action_list[self.current_action_idx]
            self.current_action_idx += 1
            self.mutex.release()
            action.exec()

    def add_path(self, robot, path = [], movement_timeout : int = None, filename = None):
        """
        Defines a list of MoveToAction to follow a list of points [(x0, y0), (x1, y1), ...]
        The path is either passed as a list of points or as a json file if filename is specified.
        These actions are added to the sequence.
        The orientation at the end of each position is not specified.
        """

        def json_to_python(filename, color):
            """
            loads a .json and returns a list [(x0, y0), (x1, y1), ...]
            make sure color is "green" or "orange"
            """
            with open(filename, "r") as f:
                result = json.loads(f.read())

            return  [(p['x'], p['y']) for p in result[color][0]['points']]

        if(not filename is None):
            path = json_to_python(filename, robot.color)

        for x, y in path:
            self.add_action(MoveToAction(robot, x, y).wait(movement_timeout))

class Function(Action):
    '''
    A function call, with the options of callback
    '''
    def __init__(self, function, args = [], callback : callable = lambda : None):
        Action.__init__(self, callback)
        if(self.callback is not None):
            self.function = lambda cb: function(*(args + [cb]))
        else:
            self.function = lambda: function(*args)

    def __str__(self):
        return "Funtion call"

    def private_exec(self):
        if(self.callback is not None):
            self.function(self.private_callback)
        else:
            #FIXME : linter error ?
            self.function()

class ThreadedFunction(Function):
    '''
    A function call in a new thread
    '''
    def __init__(self, function, args = [], callback : callable = lambda : None):
        self.thread = Thread(target = function, args = args)
        Function.__init__(self, lambda : self.thread.start(), [], callback)

class ConditionalAction(Action):
    '''
    A branching action that can trigger an action or another depending on the return value of a function
    '''
    def __init__(self,
                 condition : callable,
                 action_then : Action,
                 action_else : Action,
                 callback : callable = lambda : None):
        '''
        condition is a function that returns a boolean.
        action_then is executed if condition() returns True when the ConditionalAction is executed, action_else is executed otherwise.
        action_then or action_else may be Null.
        '''
        Action.__init__(self, callback)
        self.condition = condition
        # We have to make sure that the callback is called by the callback of the executed action
        self.action_then = action_then
        if not action_then is None:
            action_then.callback = lambda : action_then.callback(); self.private_callback()
        self.action_else = action_else
        if not action_else is None:
            action_else.callback = lambda : action_else.callback(); self.private_callback()

    def private_exec(self):
        #FIXME: ?
        if self.condition():
            if self.action_then is not None:
                self.action_then.exec()
            else:
                private_callback()
        else:
            if not self.action_else is None:
                self.action_else.exec()
            else: 
                private_callback()

class Mission():
    #TODO: docstring
    #TODO: wip
    def __init__(self, sequence : Sequence, position, estimated_points : int, estimated_time : int, timeout : int, min_date : int, max_date):
        self.sequence = sequence
        self.position = position
        self.estimated_points = estimated_points
        self.estimated_time = estimated_time
        self.timeout = timeout
        self.min_date = min_date
        self.max_date = max_date

    def exec(self):
        self.sequence.exec()

class TrueMission(Sequence):
    #Idem
    def __init__(self, position, estimated_points : int, estimated_time : int, timeout : int, min_date : int, max_date, name : str = None, callback : callable = lambda : None, abort_if_fail : bool = False):
        Sequence.__init__(name, callback, abort_if_fail)
        self.position = position
        self.estimated_points = estimated_points
        self.estimated_time = estimated_time
        self.timeout = timeout
        self.min_date = min_date
        self.max_date = max_date

class MissionStrategy:
    '''
    This class is used to make a mission choice.
    It has to be overriden in order to define the eval function.
    '''

    def __init__(self, mission_list : Iterable, robot : Robot):
        self.mission_list = mission_list

    def eval(self, mission) -> int:
        '''
        This function returns an evaluation of the quality of a mission
        at the current time.
        You need to override it.
        '''
        return 0

    def best_mission(self) -> Mission:
        '''
        This function returns the mission with the highest evaluation.
        '''

        mission_eval = [ (mission, eval(mission)) for mission in self.mission_list]
        if(len(mission_eval) == 0): return None

        sorted_missions = sorted(mission_eval, key=lambda mission: mission[2], reverse=True)

        return sorted_missions[0][0]

    def execute_best_mission(self) -> None:
        pass

####### EXAMPLES

#TODO: to move
#FIXME: actually not only examples, some tests depend on it

class MoveToAction(Function):
    '''
    Action moving to position and angle
    '''
    def __init__(self, \
                 robot, \
                 x : int, \
                 y : int, \
                 angle : int = -1):
        Function.__init__(self, robot.moveTo, [x, y, angle])


class AX12MoveAction(Function):
    '''
    Move action of an AX12
    '''
    def __init__(self, \
                 ax12 : AX12, \
                 position : int,
                 cancel_position : int = None):
        Function.__init__(self, ax12.move, [position])
        self.ax12 = ax12
        self.cancel_position = cancel_position

    def cancel_exec(self):
        if self.cancel_position is None:
            self.ax12.turn(0)
        else:
            self.ax12.move(self.cancel_position)
        Action.cancel_exec(self)
