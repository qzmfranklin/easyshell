"""An example shell, with subshell enabled.
"""

import argparse
import sys
import subprocess

from .example_shell import MyShell
from .main import update_parser

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description = __doc__,
            formatter_class = argparse.ArgumentDefaultsHelpFormatter)
    update_parser(parser)
    args = parser.parse_args()

    if args.file:
        MyShell(
                batch_mode = True,
                debug = args.debug,
                root_prompt = args.root_prompt,
                temp_dir = args.temp_dir,
        ).batch_string(args.file.read())
    else:
        d = vars(args)
        del d['file']
        MyShell(**d).cmdloop()
