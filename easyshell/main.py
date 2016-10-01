import sys

def update_parser(parser):
    """Update the parser object for the shell.

    Arguments:
        parser: An instance of argparse.ArgumentParser.
    """
    def __stdin(s):
        if s is None:
            return None
        if s == '-':
            return sys.stdin
        return open(s, 'r', encoding = 'utf8')
    parser.add_argument('--root-prompt',
            metavar = 'STR',
            default = 'PlayBoy',
            help = 'the root prompt string')
    parser.add_argument('--temp-dir',
            metavar = 'DIR',
            default = '/tmp/easyshell_demo',
            help = 'the directory to save history files')
    parser.add_argument('--debug',
            action = 'store_true',
            help = 'turn debug infomation on')
    parser.add_argument('file',
            metavar = 'FILE',
            nargs = '?',
            type = __stdin,
            help = "execute script in non-interactive mode. '-' = stdin")
