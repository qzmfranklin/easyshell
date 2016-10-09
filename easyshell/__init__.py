from .base import deprecated, isdeprecated, \
        command, iscommand, \
        isvisiblecommand, isinternalcommand, \
        helper, ishelper, \
        completer, iscompleter, \
        subshell
from .basic_shell import BasicShell
from .debugging_shell import DebuggingShell
from .example_shell import MyShell
from .shell import Shell
