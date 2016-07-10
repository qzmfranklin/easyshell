#  A python3 library for creating recursive shells.
#
#  Copyright (C) 2016,  Zhongming Qu
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""A generic class to build line-oriented command interpreters.
"""

import copy
import inspect
import os
import pprint
import readline
import shlex
import shutil
import string
import subprocess
import sys
import tempfile
import textwrap
import traceback


# Decorators with arguments is a little bit tricky to get right. A good
# thread on it is:
#       http://stackoverflow.com/questions/5929107/python-decorators-with-parameters
def command(*commands, is_visible = True, is_internal = False):
    """Decorate a function to be the entry function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.
        is_visible: This command is visible in tab completions.
        is_internal: The lexing rule is unchanged even if the parse_line()
            method is overloaded in the subclasses.

    ----------------------------
    Interface of command methods:

        @command('foo', 'bar')
        def bar(self, args):
            '''The method invoked by 'foo' and 'bar' commands.

            Arguments:
                args: A list of strings. This list is obtianed via
                    shlex.split().
            '''
            pass
    """
    def decorated_func(f):
        f.__command__ = {
                'commands': list(commands),
                'is_visible': is_visible,
                'is_internal': is_internal,
        }
        return f
    return decorated_func


# The naming convention is same as the inspect module, which has such predicate
# methods as isfunction, isclass, ismethod, etc..
def iscommand(f):
    """Is the function object a command or not."""
    return hasattr(f, '__command__')


def getcommands(f):
    """Get the list of commands that this function object is registered for."""
    return f.__command__['commands']


def isvisiblecommand(f):
    """Is the function object a visible command or not."""
    return getattr(f, '__command__')['is_visible']


def isinternalcommand(f):
    """Is the function object an internal command or not."""
    return getattr(f, '__command__')['is_internal']


def helper(*commands):
    """Decorate a function to be the helper function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.

    ---------------------------
    Interface of helper methods:

        @helper('some-command')
        def help_foo(self, args):
            '''
            Arguments:
                args: A list of arguments.

            Returns:
                A string that is the help message.
            '''
            pass
    """
    def decorated_func(f):
        f.__help_targets__ = list(commands)
        return f
    return decorated_func


def ishelper(f):
    """Is the function object a helper function or not."""
    return hasattr(f, '__help_targets__')


def completer(*commands):
    """Decorate a function to be the completer function of commands.

    Arguments:
        commands: Names of command that should trigger this function object.

    ------------------------------
    Interface of completer methods:

        @completer('some-other_command')
        def complete_foo(self, args, text):
            '''
            Arguments:
                args: A list of arguments. The first token, i.e, the command
                    itself, is not included.
                text: The scope of text being replaced.

                A few examples, with '$' representing the shell prompt and
                '|' represents the cursor position:
                        $ |
                        $ history|
                            handled by the __driver_completer() method
                        $ history |
                            args = []
                            text = ''
                        $ history cle|
                            args = []
                            text = 'cle'
                        $ history clear |
                            args = ['clear']
                            text = ''

            Returns:
                A list of candidates. If no candidate was found, return
                either [] or None.
            '''
            pass
    """
    def decorated_func(f):
        f.__complete_targets__ = list(commands)
        return f
    return decorated_func


def iscompleter(f):
    """Is the function object a completer function or not."""
    return hasattr(f, '__complete_targets__')


# A parametrized decorator decorating a method is very tricky. To fully
# understand, please first consult this thread:
#       http://stackoverflow.com/questions/11731136/python-class-method-decorator-w-self-arguments
# Then note that when the method being decorated is printed, its __name__
# attribute is unchanged but the repr() function displays the method as
# 'inner_func'.
def subshell(shell_cls, *commands, **kwargs):
    """Decorate a function to launch a ShellBase subshell.

    Arguments:
        shell_cls: A subclass of ShellBase to be launched.
        commands: Names of command that should trigger this function object.
        kwargs: The keyword arguments for the command decorator method.

    -----------------------------
    Interface of subshell methods:

        @command(SomeShellClass, 'foo')
        def bar(self, args):
            '''The command 'foo' invokes this method then launches the subshell.

            Arguments:
                args: A list of strings. This list is obtianed via
                    shlex.split().

            Returns:
                A string used as the prompt.
            '''
            pass
    """
    def decorated_func(f):
        def inner_func(self, cmd, args):
            prompt_display = f(self, cmd, args)
            return self.launch_subshell(shell_cls, args,
                    prompt_display = prompt_display)
        inner_func.__name__ = f.__name__
        obj = command(*commands)(inner_func, **kwargs) if commands else inner_func
        obj.__launch_subshell__ = shell_cls
        return obj
    return decorated_func


def issubshellcommand(f):
    """Does the function object launch a subshell or not."""
    return hasattr(f, '__launch_subshell__')

class ShellBase(object):

    """Base shell class.

    This class implements the following core infrastructures:
          - Recursively launch subshell.
          - Register commands, helpers, and completers.
          - The ?<TAB> help experience.

    Subclasses in the same module must implement a few command methods and
    completer methods to become a functional shell:
          - __exec__ (hidden)
          - exit
          - history
    """

    class _Mode(object):
        """Stack mode information used when entering and leaving a subshell.
        """
        def __init__(self, args, prompt_display):
            self.args = args
            self.prompt_display = prompt_display

    EOF = chr(ord('D') - 64)

    # These characters are not treated as delimiters.
    #   char    |       rationale
    # ----------+--------------------------------------------------------
    #     -     |  Allow commands to contain '-'.
    _non_delims = '-'

    def __init__(self, *,
            debug = False,
            mode_stack = [],
            root_prompt = 'root',
            stdout = sys.stdout,
            stderr = sys.stderr,
            temp_dir = None):
        """Instantiate a line-oriented interpreter framework.

        Arguments:
            debug: If True, print_debug() prints to self.stderr.
            mode_stack: A stack of ShellBase._Mode objects.
            root_prompt: The root prompt.
            stdout, stderr: The file objects to write to for output and error.
            temp_dir: The temporary directory to save history files. The default
                value, None, means to generate such a directory.
        """
        self.debug = debug
        self.stdout = stdout
        self.stderr = stderr
        self._mode_stack = mode_stack
        self.root_prompt = root_prompt
        self._temp_dir = temp_dir if temp_dir else tempfile.mkdtemp()
        os.makedirs(os.path.join(self._temp_dir, 'history'), exist_ok = True)

        readline.parse_and_bind('tab: complete')

        # Even though __build_XXX_map() methods are class methods, they must be
        # called via self. Otherwise they cannot find the commands.
        self._cmd_map_all, self._cmd_map_visible, self._cmd_map_internal = self.__build_cmd_maps()
        self._helper_map = self.__build_helper_map()
        self._completer_map = self.__build_completer_map()

        self.__completion_candidates = []

    @classmethod
    def doc_string(cls):
        """Get the doc string of this class.

        If this class does not have a doc string or the doc string is empty, try
        its base classes until the root base class, ShellBase, is reached.

        CAVEAT:
            This method assumes that this class and all its super classes are
            derived from ShellBase or object.
        """
        clz = cls
        while not clz.__doc__:
            clz = clz.__bases__[0]
        return clz.__doc__

    @property
    def prompt(self):
        return '({})$ '.format('-'.join(
                [ self.root_prompt ] + \
                [ m.prompt_display for m in self._mode_stack ]))

    @property
    def history_fname(self):
        """The temporary for storing the history of this shell."""
        return os.path.join(self._temp_dir, 'history', 's-' + self.prompt[1:-2])

    def print_debug(self, msg):
        if self.debug:
            print(msg, file = self.stderr)

    def launch_subshell(self, shell_cls, args, *, prompt_display = None):
        """Launch a subshell.

        The doc string of the cmdloop() method explains how shell histories and
        history files are saved and restored.

        The design of the ShellBase class encourage launching of subshells through
        the subshell() decorator function. Nonetheless, the user has the option
        of directly launching subshells via this method.

        Arguments:
            shell_cls: The ShellBase class object to instantiate and launch.
            args: Arguments used to launch this subshell.
            prompt_display: The name of the subshell. The default, None, means
                to use the shell_cls.__name__.

        Returns:
            'end': Inform the parent shell to keep exiting until the root shell
                is reached.
            False, None, or anything that are evaluated as False: Inform the
                parent shell to stay in that parent shell.
        """
        # Save history of the current shell.
        readline.write_history_file(self.history_fname)

        prompt_display = prompt_display if prompt_display else shell_cls.__name__
        mode = ShellBase._Mode(args, prompt_display)
        shell = shell_cls(
                debug = self.debug,
                mode_stack = self._mode_stack + [ mode ],
                root_prompt = self.root_prompt,
                stdout = self.stdout,
                stderr = self.stderr,
                temp_dir = self._temp_dir,
        )
        # The subshell creates its own history context.
        self.print_debug("Leave parent shell '{}'".format(self.prompt))
        exit_directive = shell.cmdloop()
        self.print_debug("Enter parent shell '{}': {}".format(self.prompt, exit_directive))

        # Restore history. The subshell could have deleted the history file of
        # this shell via 'history clearall'.
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)

        return 'end' if exit_directive == 'end' else False

    def preloop(self):
        pass

    def postloop(self):
        pass

    def cmdloop(self):
        """Start the main loop of the interactive shell.

        The preloop() and postloop() methods are always run before and after the
        main loop, respectively.

        Returns:
            'end': Inform the parent shell to to keep exiting until the root
                shell is reached.
            False, None, or anything that are evaluated as False: Exit this
                shell, enter the parent shell.

        History:

            ShellBase histories are persistently saved to files, whose name matches
            the prompt string. For example, if the prompt of a subshell is
            '(Foo-Bar-Kar)$ ', the name of its history file is s-Foo-Bar-Kar.
            The history_fname property encodes this algorithm.

            All history files are saved to the the directory whose path is
            self._temp_dir. Subshells use the same temp_dir as their parent
            shells, thus their root shell.

            The history of the parent shell is saved and restored by the parent
            shell, as in launch_subshell(). The history of the subshell is saved
            and restored by the subshell, as in cmdloop().

            When a subshell is started, i.e., when the cmdloop() method of the
            subshell is called, the subshell will try to load its own history
            file, whose file name is determined by the naming convention
            introduced earlier.

        Completer Delimiters:

            Certain characters such as '-' could be part of a command. But by
            default they are considered the delimiters by the readline library,
            which causes completion candidates with those characters to
            malfunction.

            The old completer delimiters are saved before the loop and restored
            after the loop ends. This is to keep the environment clean.
        """
        self.print_debug("Enter subshell '{}'".format(self.prompt))

        # Save the completer function, the history buffer, and the
        # completer_delims.
        old_completer = readline.get_completer()
        old_delims = readline.get_completer_delims()
        new_delims = ''.join(list(set(old_delims) - set(ShellBase._non_delims)))
        readline.set_completer_delims(new_delims)

        # Load the new completer function and start a new history buffer.
        readline.set_completer(self.__driver_stub)
        readline.clear_history()
        if os.path.isfile(self.history_fname):
            readline.read_history_file(self.history_fname)

        # main loop
        try:
            # The exit_directive could be one { True, False, 'end' }.
            #       True:   Leave this shell, enter the parent shell.
            #       False:  Continue with the loop.
            #       'end':  Exit to the root shell.
            # TODO: For the above logic, the if-elif statements in the while
            # loop seems a bit convoluted.  Maybe it could be cleaner.
            exit_directive = False
            self.preloop()
            while True:
                if exit_directive == 'end':
                    if self._mode_stack:
                        break
                elif exit_directive == True:
                    break
                try:
                    line = input(self.prompt).strip()
                except EOFError:
                    line = ShellBase.EOF

                try:
                    exit_directive = self.__exec_line__(line)
                except:
                    self.stderr.write(traceback.format_exc())
        finally:
            self.postloop()
            # Restore the completer function, save the history, and restore old
            # delims.
            readline.set_completer(old_completer)
            readline.write_history_file(self.history_fname)
            readline.set_completer_delims(old_delims)

        self.print_debug("Leave subshell '{}': {}".format(self.prompt, exit_directive))

        return exit_directive

    def __exec_line__(self, line):
        """Execute the input line.

        emptyline: no-op
        unknown command: print error message
        known command: invoke the corresponding method

        The parser method, parse_line(), can be overriden in subclasses to
        apply different parsing rules. Please refer to the doc string of
        parse_line() for complete information.

        Arguments:
            line: A string, representing a line of input from the shell. This
                string is preprocessed by cmdloop() to convert the EOF character
                to '\\x04', i.e., 'D' - 64, if the EOF character is the only
                character from the shell.
        """
        if not line:
            return

        cmd, args = ( '', [] )

        toks = shlex.split(line)
        if not toks:
            return

        if line == ShellBase.EOF:
            # This is a hack to allow the EOF character to behave exactly like
            # typing the 'exit' command.
            readline.insert_text('exit\n')
            readline.redisplay()
            cmd = 'exit'
        elif toks and toks[0] in self._cmd_map_internal.keys():
            cmd = toks[0]
            args = toks[1:] if len(toks) > 1 else []
        else:
            cmd, args = self.parse_line(line)

        if not cmd in self._cmd_map_all.keys():
            self.stderr.write("{}: command not found\n".format(cmd))
            return

        func_name = self._cmd_map_all[cmd]
        func = getattr(self, func_name)
        return func(cmd, args)

    def parse_line(self, line):
        """Parse a line of input.

        The input line is tokenized using the same rules as the way bash shell
        tokenizes inputs. All quoting and escaping rules from the bash shell
        apply here too.

        The following cases are handled by __exec_line__():
            1.  Empty line.
            2.  The input line is completely made of whitespace characters.
            3.  The input line is the EOF character.
            4.  The first token, as tokenized by shlex.split(), is '!'.
            5.  Internal commands, i.e., commands registered with
                    is_internal = True

        Arguments:
            The line to parse.

        Returns:
            A tuple (cmd, args). The first element cmd must be a python3 string.
            The second element is, by default, a list of strings representing
            the arguments, as tokenized by shlex.split().

        How to overload parse_line():
            1.  The signature of the method must be the same.
            2.  The return value must be a tuple (cmd, args), where the cmd is
                a string representing the first token, and args is a list of
                strings.
        """
        toks = shlex.split(line)
        # Safe to index the 0-th element because this line would have been
        # parsed by __exec_line__ if toks is an empty list.
        return ( toks[0], [] if len(toks) == 1 else toks[1:] )

    def __driver_stub(self, text, state):
        """Display help messages or invoke the proper completer.

        The interface of helper methods and completer methods are documented in
        the helper() decorator method and the completer() decorator method,
        respectively.

        Arguments:
            text: A string, that is the current completion scope.
            state: An integer.

        Returns:
            A string used to replace the given text, if any.
            None if no completion candidates are found.

        Raises:
            This method is called via the readline callback. If this method
            raises an error, it is silently ignored by the readline library.
            This behavior makes debugging very difficult. For this reason,
            non-driver methods are run within try-except blocks. When an error
            occurs, the stack trace is printed to self.stderr.
        """
        origline = readline.get_line_buffer()
        line = origline.lstrip()
        if line and line[-1] == '?':
            self.__driver_helper(line)
        else:
            toks = shlex.split(line)
            return self.__driver_completer(toks, text, state)

    def __driver_completer(self, toks, text, state):
        """Driver level completer.

        Arguments:
            toks: A list of tokens, tokenized from the original input line.
            text: A string, the text to be replaced if a completion candidate is chosen.
            state: An integer, the index of the candidate out of the list of candidates.

        Returns:
            A string, the candidate.

        """
        if state != 0:
            return self.__completion_candidates[state]

        # Update the cache when this method is first called, i.e., state == 0.

        # If the line is empty or the user is still inputing the first token,
        # complete with available commands.
        if not toks or (len(toks) == 1 and text):
            try:
                self.__completion_candidates = self.__complete_cmds(text)
            except:
                self.stderr.write('\n')
                self.stderr.write(traceback.format_exc())
                self.__completion_candidates = []
            return self.__completion_candidates[state]

        # Otherwise, try to complete with the registered completer method.
        cmd = toks[0]
        args = toks[1:] if len(toks) > 1 else None
        if text and args:
            del args[-1]
        if cmd in self._completer_map.keys():
            completer_name = self._completer_map[cmd]
            completer_method = getattr(self, completer_name)
            try:
                self.__completion_candidates = completer_method(cmd, args, text)
            except:
                self.stderr.write('\n')
                self.stderr.write(traceback.format_exc())
                self.__completion_candidates = []

        return self.__completion_candidates[state]

    def __complete_cmds(self, text):
        """Get the list of commands whose names start with a given text."""
        return [ name for name in self._cmd_map_visible.keys() if name.startswith(text) ]

    def __driver_helper(self, line):
        """Driver level helper method.

        1.  Display help message for the given input. Internally calls
            self.__get_help_message() to obtain the help message.
        2.  Re-display the prompt and the input line.

        Arguments:
            line: The input line.

        Raises:
            Errors from helper methods print stack trace without terminating
            this shell. Other exceptions will terminate this shell.
        """
        if line.strip() == '?':
            self.stdout.write('\n')
            self.stdout.write(self.doc_string())
        else:
            toks = shlex.split(line[:-1])
            try:
                msg = self.__get_help_message(toks)
            except Exception as e:
                self.stderr.write('\n')
                self.stderr.write(traceback.format_exc())
                self.stderr.flush()
            self.stdout.write('\n')
            self.stdout.write(msg)
        # Restore the prompt and the original input.
        self.stdout.write('\n')
        self.stdout.write(self.prompt)
        self.stdout.write(line)
        self.stdout.flush()

    def __get_help_message(self, toks):
        """Write help message to file.

        Only called by the __driver_helper() method.

        Looks for the help message in the following order:

            1.  The helper method registered with this command via the @helper
                decorator.
            2.  The doc string of the registered method.
            3.  A default help message basically saying 'no help found'.

        Arguments:
            toks: The list of command followed by its arguments.
            fp: The file-like object to write help messages to.

        Returns:
            The help message.

        Raises:
             As this function is called via the readline complete callback, any
             errors and exceptions are silently ignored.
        """
        cmd = toks[0]
        if cmd in self._helper_map.keys():
            helper_name = self._helper_map[cmd]
            helper_method = getattr(self, helper_name)
            args = toks[1:] if len(toks) > 1 else []
            return helper_method(cmd, args)

        if cmd in self._cmd_map_all.keys():
            name = self._cmd_map_all[cmd]
            method = getattr(self, name)
            return textwrap.dedent(method.__doc__)

        return textwrap.dedent('''\
                       No help message is found for:
                       {}
                       '''.format(textwrap.indent(
                           subprocess.list2cmdline(toks), '    ')))


    ################################################################################
    # _build_XXX_map() methods are only used by ShellBase.__init__() method.
    # TODO: The internal logic looks so similar. Should consider merging these
    # methods.
    ################################################################################

    @classmethod
    def __build_cmd_maps(cls):
        """Build the mapping from command names to method names.

        One command name maps to at most one method.
        Multiple command names can map to the same method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Returns:
            A tuple (cmd_map, hidden_cmd_map, internal_cmd_map).
        """
        cmd_map_all = {}
        cmd_map_visible = {}
        cmd_map_internal = {}
        for name in dir(cls):
            obj = getattr(cls, name)
            if iscommand(obj):
                for cmd in getcommands(obj):
                    if cmd in cmd_map_all.keys():
                        raise PyShellError("The command '{}' already has cmd"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, cmd_map_all[cmd], obj.__name__))
                    cmd_map_all[cmd] = obj.__name__
                    if isvisiblecommand(obj):
                        cmd_map_visible[cmd] = obj.__name__
                    if isinternalcommand(obj):
                        cmd_map_internal[cmd] = obj.__name__
        return cmd_map_all, cmd_map_visible, cmd_map_internal

    @classmethod
    def __build_helper_map(cls):
        """Build a mapping from command names to helper names.

        One command name maps to at most one helper method.
        Multiple command names can map to the same helper method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Raises:
            PyShellError: A command maps to multiple helper methods.
        """
        ret = {}
        for name in dir(cls):
            obj = getattr(cls, name)
            if ishelper(obj):
                for cmd in obj.__help_targets__:
                    if cmd in ret.keys():
                        raise PyShellError("The command '{}' already has helper"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, ret[cmd], obj.__name__))
                    ret[cmd] = obj.__name__
        return ret

    @classmethod
    def __build_completer_map(cls):
        """Build a mapping from command names to completer names.

        One command name maps to at most one completer method.
        Multiple command names can map to the same completer method.

        Only used by __init__() to initialize self._cmd_map. MUST NOT be used
        elsewhere.

        Raises:
            PyShellError: A command maps to multiple helper methods.
        """
        ret = {}
        for name in dir(cls):
            obj = getattr(cls, name)
            if iscompleter(obj):
                for cmd in obj.__complete_targets__:
                    if cmd in ret.keys():
                        raise PyShellError("The command '{}' already has"
                                           " complter"
                                           " method '{}', cannot register a"
                                           " second method '{}'.".format( \
                                                    cmd, ret[cmd], obj.__name__))
                    ret[cmd] = obj.__name__
        return ret


class _BasicShell(ShellBase):

    """Implement built-in commands."""

    @command('!', is_internal = True, is_visible = False)
    def _do_exec(self, cmd, args):
        """Execute a command using subprocess.Popen().
        """
        if not args:
            self.stderr.write("run: empty command\n")
            return
        proc = subprocess.Popen(subprocess.list2cmdline(args),
                shell = True, stdout = self.stdout)
        proc.wait()

    @command('end', 'exit', is_internal = True)
    def _do_exit(self, cmd, args):
        """\
        Exit shell.
            exit | C-D          Exit to the parent shell.
            exit root | end     Exit to the root shell.
        """
        if cmd == 'end':
            return 'end'
        if args and args[0] == 'root':
            return 'end'
        elif not args:
            return True
        else:
            self.stdout.write(textwrap.dedent('''\
                    exit: unrecognized arguments: {}
                    ''')).format(subprocess.list2cmdline(args))

    @completer('exit')
    def _complete_exit(self, cmd, args, text):
        """Find candidates for the 'exit' command."""
        if args:
            return
        return [ x for x in { 'root', } \
                if x.startswith(text) ]

    @command('history', is_internal = True)
    def _do_history(self, cmd, args):
        """\
        Display history.
            history             Display history.
            history clear       Clear history.
            history clearall    Clear history for all shells.
        """
        if args and args[0] == 'clear':
            readline.clear_history()
            readline.write_history_file(self.history_fname)
        elif args and args[0] == 'clearall':
            readline.clear_history()
            shutil.rmtree(self._temp_dir, ignore_errors = True)
            os.makedirs(os.path.join(self._temp_dir, 'history'))
        else:
            readline.write_history_file(self.history_fname)
            with open(self.history_fname, 'r', encoding = 'utf8') as f:
                self.stdout.write(f.read())

    @completer('history')
    def _complete_history(self, cmd, args, text):
        """Find candidates for the 'history' command."""
        if args:
            return
        return [ x for x in { 'clear', 'clearall' } \
                if x.startswith(text) ]


class _DebuggingShell(_BasicShell):

    """Debugging shell.

    DISCLAIMER: This debugging shell is still highly experimental.

    Lexer is changed. For example, '  foo   dicj didiw  ' is tokenized as
            [ 'foo', '   dicj didiw  ' ]

    Available commands:
            p               Display object.
            e               Evaluate python code.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from ._python_completer import Completer
        self.__python_completer = Completer()

    # TODO: This completer is not fully functional.
    @completer('p')
    def _complete_print(self, cmd, arg, text):
        return self.__python_completer.find_matches(text)

    # TODO: This method is not fully implemented yet.
    @command('p')
    def _do_print(self, cmd, args):
        """\
        Display symbols.
            p               Display names of inspectable objects.
            p <id>          Display the content of an object.
        """
        name = args[0].strip()
        if not name:
            self.stderr.write('TODO: Display names of inspectable objects.\n')
            return
        try:
            code = textwrap.dedent('''
                    self.stdout.write(name + ':\\n' + textwrap.indent(pprint.pformat({}), '    ') + '\\n')
                    ''').format(name).strip()
            eval(code, globals(), locals())
        except NameError:
            self.stderr.write("p: name '{}' is not defined\n".format(name))
        self.stdout.flush()


    # TODO: Use proper namespace for the dyncamic evaluation. According to the
    # current implementation existing variables may be overwritten.
    @command('e')
    def _do_eval(self, cmd, args):
        """\
        Evaluate python code.
            e <expr>        Evaluate <expr>.
        """
        code = args[0].lstrip()
        if not code:
            self.stderr.write('e: cannot evalutate empty expression\n')
            return
        try:
            eval(code)
        except:
            self.stderr.write('''When executing code '{}', the following error was raised:\n\n'''.format(code))
            self.stderr.write(textwrap.indent(traceback.format_exc(), '    '))


    def parse_line(self, line):
        """Parser for the debugging shell.

        Treat everything after the first token as one literal entity. Whitespace
        characters between the first token and the next first non-whitespace
        character are preserved.

        For example, '  foo   dicj didiw  ' is parsed as
            ( 'foo', '   dicj didiw  ' )

        Returns:
            A tuple (cmd, args), where the args is a list that consists of one
            and only one string containing everything after the cmd as is.
        """
        line = line.lstrip()
        toks = shlex.split(line)
        cmd = toks[0]
        arg = line[len(cmd):]
        return cmd, [ arg, ]


class _Shell(_BasicShell):

    """Embed _DebuggingShell into _BasicShell."""

    @subshell(_DebuggingShell, 'debug')
    def _do_debug(self, cmd, args):
        """Enter the debugging shell."""
        return 'DEBUG'


class Shell(_Shell):

    """Emacs-like recursive shell.

    Get help:
            <TAB>               Display commands.
            ?<TAB>              Display this message.
            <command>?<TAB>     Display help message for <command>.

    Execute a command in the Linux shell:
            ! <command>         Execute <command> using subprocess.Popen().
    """
    pass
