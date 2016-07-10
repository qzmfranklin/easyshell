import glob
import os

def find_matches(text):
    """Find matching files for text.

    For this completer to function in Unix systems, the readline module must not
    treat \\ and / as delimiters.
    """
    pattern = os.path.expanduser(text) + '*'
    is_implicit_cwd = text.startswith('/') or text.startswith('./')
    if is_implicit_cwd:
        pattern = './' + pattern
    rawlist = glob.glob(pattern)
    if is_implicit_cwd:
        return [ fname[2:] for fname in rawlist ]
    else:
        return rawlist
