#!/usr/bin/env python3
#
# This file is part of Script of Scripts (SoS), a workflow system
# for the execution of commands and scripts in different languages.
# Please visit https://github.com/bpeng2000/SOS for more information.
#
# Copyright (C) 2016 Bo Peng (bpeng@mdanderson.org)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
import os
import sys
import re
import copy
import time
import types
import logging
import glob
import collections
import traceback
import pickle
import yaml
import psutil
import urllib
import blessings
import subprocess
from io import StringIO
from html.parser import HTMLParser

__all__ = ['logger', 'get_output']


class ColoredFormatter(logging.Formatter):
    ''' A logging formatter that uses color to differntiate logging messages
    and emphasize texts. Texts that would be empahsized are quoted with
    double backslashes (`` ``).
    '''
    def __init__(self, msg):
        logging.Formatter.__init__(self, msg)
        #
        # color for different logging levels. The current terminal color
        # is used for INFO
        self.LEVEL_COLOR = {
            'TRACE': 'DARK_CYAN',
            'DEBUG': 'BLUE',
            'WARNING': 'PURPLE',
            'ERROR': 'RED',
            'CRITICAL': 'RED_BG',
        }
        self.COLOR_CODE={
            'ENDC':0,  # RESET COLOR
            'BOLD':1,
            'UNDERLINE':4,
            'BLINK':5,
            'INVERT':7,
            'CONCEALD':8,
            'STRIKE':9,
            'GREY30':90,
            'GREY40':2,
            'GREY65':37,
            'GREY70':97,
            'GREY20_BG':40,
            'GREY33_BG':100,
            'GREY80_BG':47,
            'GREY93_BG':107,
            'DARK_RED':31,
            'RED':91,
            'RED_BG':41,
            'LIGHT_RED_BG':101,
            'DARK_YELLOW':33,
            'YELLOW':93,
            'YELLOW_BG':43,
            'LIGHT_YELLOW_BG':103,
            'DARK_BLUE':34,
            'BLUE':94,
            'BLUE_BG':44,
            'LIGHT_BLUE_BG':104,
            'DARK_MAGENTA':35,
            'PURPLE':95,
            'MAGENTA_BG':45,
            'LIGHT_PURPLE_BG':105,
            'DARK_CYAN':36,
            'AUQA':96,
            'CYAN_BG':46,
            'LIGHT_AUQA_BG':106,
            'DARK_GREEN':32,
            'GREEN':92,
            'GREEN_BG':42,
            'LIGHT_GREEN_BG':102,
            'BLACK':30,
        }

    def colorstr(self, astr, color):
        return '\033[{}m{}\033[{}m'.format(color, astr,
            self.COLOR_CODE['ENDC'])

    def emphasize(self, msg, level_color=0):
        # display text within `` and `` in green
        return re.sub(r'``([^`]*)``', '\033[32m\\1\033[{}m'.format(level_color), str(msg))

    def format(self, record):
        level_name = record.levelname
        if level_name in self.LEVEL_COLOR:
            level_color = self.COLOR_CODE[self.LEVEL_COLOR[level_name]]
            record.color_levelname = self.colorstr(level_name, level_color)
            record.color_name = self.colorstr(record.name, self.COLOR_CODE['BOLD'])
            record.color_msg = self.colorstr(self.emphasize(record.msg, level_color), level_color)
        else:
            # for INFO, use default color
            record.color_levelname = record.levelname
            record.color_msg = self.emphasize(record.msg)
        return logging.Formatter.format(self, record)


def shortRepr(obj, noneAsNA=False):
    '''Return a short representation of obj for clarity.'''
    if obj is None:
        return 'unspecified' if noneAsNA else 'None'
    elif isinstance(obj, str) and len(obj) > 50:
        return '{}...'.format(obj[:40].replace('\n', '\\n'))
    elif isinstance(obj, (str, int, float, bool)) or (isinstance(obj, collections.Sequence) \
        and len(obj) <= 2) or len(str(obj)) < 50:
        return repr(obj)
    elif isinstance(obj, collections.Sequence): # should be a list or tuple
        return repr(obj).split(' ')[0] + ' ...] ({} items)'.format(len(obj))
    elif isinstance(obj, dict):
        first_key = obj.keys()[0]
        return '{{{!r}:{!r}, ...}} ({} items)'.format(first_key, obj[first_key], len(obj))
    else:
        return '{}...'.format(repr(obj)[:40])

#
# SoS Workflow dictionary
#
class WorkflowDict(object):
    """A dictionary object that
    1. Generate logging message for debugging purposes.
    2. Generate warning message if ALLCAP variables are changed.

    IMPORTANT:

    Python does not allow the passing of a derived class of dict as globals
    to eval or exec. Doing so will result in strange behavior such as __builtins__
    not found. We then have to embed a real dictionary in WorkflowDict instead of
    deriving a dict from it.
    """
    def __init__(self, *args, **kwargs):
        self._dict = dict(*args, **kwargs)
        self._readonly_vars = {}

    def set(self, key, value):
        '''A short cut to set value to key without triggering any logging
        or warning message.'''
        self._check_readonly(key, value)
        self._dict[key] = value

    def quick_update(self, obj):
        '''Update without readonly check etc. For fast internal update'''
        self._dict.update(obj)

    def update(self, obj):
        '''Redefine update to trigger logging message'''
        for k,v in obj.items():
            self._check_readonly(k, v)
        #
        self._dict.update(obj)
        for k, v in obj.items():
            if env.verbosity > 2:
                self._log(k, v)

    def __contains__(self, key):
        return key in self._dict

    def __getattr__(self, attr):
        # for attributes that cannot be found, default to dictionary attribute
        # (e.g. keys, pop, get...)
        return getattr(self._dict, attr)

    def __getitem__(self, key):
        return self._dict[key]

    def __setitem__(self, key, value):
        '''Set value to key, trigger logging and warning messages if needed'''
        if env.verbosity > 2:
            self._log(key, value)
        if env.run_mode == 'inspect':
            self._warn(key, value)
        if key in ('input', 'output', 'depends', '_input', '_output', '_depends', '_runtime'):
            raise ValueError('Variable {} can only be set by SoS'.format(key))
        self.set(key, value)

    def check_readonly_vars(self):
        for key in env.readonly_vars:
            if key in self._readonly_vars:
                if self._dict[key] != self._readonly_vars[key]:
                    if '__interactive__' in env.sos_dict and env.sos_dict['__interactive__']:
                        env.logger.warning('readonly variable {} is changed from {} to {}'
                            .format(key, self._dict[key], self._readonly_vars[key]))
                        self._readonly_vars[key] = self._dict[key]
                    else:
                        raise RuntimeError('Variable {} is readonly and cannot be changed from {} to {}.'
                            .format(key, self._dict[key], self._readonly_vars[key]))
            elif key in self._dict:
                self._readonly_vars[key] = self._dict[key]

    def _check_readonly(self, key, value):
        if key in env.readonly_vars:
            if key not in self._readonly_vars:
                self._readonly_vars[key] = value
            # if the key already exists
            if key in self._dict:
                if self._dict[key] != self._readonly_vars[key]:
                    if '__interactive__' in env.sos_dict and env.sos_dict['__interactive__']:
                        env.logger.warning('readonly variable {} is changed from {} to {}'
                            .format(key, self._dict[key], self._readonly_vars[key]))
                        self._readonly_vars[key] = self._dict[key]
                    else:
                        raise RuntimeError('Variable {} is readonly and cannot be changed from {} to {}.'
                            .format(key, self._dict[key], self._readonly_vars[key]))
                if value != self._dict[key]:
                    if '__interactive__' in env.sos_dict and env.sos_dict['__interactive__']:
                        env.logger.warning('readonly variable {} is changed from {} to {}'
                            .format(key, self._dict[key], value))
                        self._dict[key] = value
                    else:
                        raise RuntimeError('Variable {} is readonly and cannot be changed from {} to {}.'
                            .format(key, self._dict[key], value))

    def _log(self, key, value):
        env.logger.debug('``{}`` = ``{}``'.format(key, shortRepr(value)))

    def _warn(self, key, value):
        if key.isupper() and key in self._dict and self._dict[key] != value:
            env.logger.warning('Changing readonly variable {} from {} to {}'
                .format(key, self._dict[key], value))
        if key.startswith('_') and not key.startswith('__') and key not in ('_input', '_output', '_step', '_index', '_depends', '_runtime'):
            env.logger.warning('{}: Variables with leading underscore is reserved for SoS temporary variables.'.format(key))

    def clone_pickleable(self):
        '''Return a copy of the existing dictionary but keep only the ones that are pickleable'''
        return {x:copy.deepcopy(y) for x,y in self._dict.items() if pickleable(y)}
#
# Runtime environment
#
class RuntimeEnvironments(object):
    '''A singleton object that provides runtime environment for SoS.
    Atributes of this object include:

    logger:
        a logging object

    verbosity:
        a verbosity level object that sets the verbosity level of the logger

    logfile:
        name of logfile for the logger. default to no logfile.

    '''
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RuntimeEnvironments, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        self.reset()

    def reset(self):
        # logger
        self._logger = None
        self._verbosity = 2
        self._logfile = None
        self._set_logger()
        #
        # run mode, this mode controls how SoS actions behave
        #
        self.run_mode = 'run'
        #
        # signature mode can be
        #
        # default              (save signature, skip if signature match)
        # ignore               (ignore existing signature but still saves signature)
        # assert               (verify existing signature and fail if signature mismatch)
        # construct            (reconstruct signature from existing output files)
        self.sig_mode = 'default'
        #
        # global dictionaries used by SoS during the
        # execution of SoS workflows
        self.sos_dict = WorkflowDict()
        # variables that are defined in global and parameters sections and are readonly
        self.readonly_vars = set()
        #
        # a list of variables that will be sent back from subprocess
        # in addition to aliased stepinfo. This is designed for testing
        # purposes only
        self.shared_vars = set()
        # maximum number of concurrent jobs
        self.max_jobs = 1
        self.running_jobs = 0
        # this directory will be used by a lot of processes
        self.exec_dir = os.getcwd()
        if not os.path.isdir('.sos'):
            os.mkdir('.sos')

    def register_process(self, pid, msg=''):
        '''Register a process used by this SoS instance. It will also be
        used to check resource used.'''
        proc_file = os.path.join(self.exec_dir, '.sos/proc_{}'.format(pid))
        self.logger.trace('Register {} {}'.format(pid, msg))
        with open(proc_file, 'w') as p:
            p.write(msg)

    def deregister_process(self, pid):
        proc_file = os.path.join(self.exec_dir, '.sos/proc_{}'.format(pid))
        self.logger.trace('Deregister {} at {}'.format(pid, proc_file))
        if os.path.isfile(proc_file):
            os.remove(proc_file)

    def cleanup(self):
        '''Clean up all running processes'''
        for p in glob.glob(os.path.join(self.exec_dir, '.sos/proc_*')):
            pid = int(os.path.basename(p)[5:])
            try:
                env.logger.trace('Killing {} and all its children'.format(pid))
                # psutil might not exist if SoS is not properly installed
                # but we are not acting like the end of world here
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
            except Exception as e:
                env.logger.debug(e)
            os.remove(p)

    #
    # attribute logger
    #
    def _set_logger(self, unused=None):
        if not hasattr(logging, 'TRACE'):
            logging.TRACE = 5
            logging.addLevelName(logging.TRACE, "TRACE")
        # create a logger, we current use the regular logger but we should
        # switch to multiprocessing.get_logger if we notice trouble in, for example,
        # logging from multiple processes.
        self._logger = logging.getLogger()
        # clear previous handler
        for handler in self._logger.handlers:
            self._logger.removeHandler(handler)
        self._logger.setLevel(logging.DEBUG)
        # output to standard output
        cout = logging.StreamHandler()
        levels = {
            0: logging.ERROR,
            1: logging.WARNING,
            2: logging.INFO,
            3: logging.DEBUG,
            4: logging.TRACE,
            None: logging.INFO
        }
        #
        cout.setLevel(levels[self._verbosity])
        cout.setFormatter(ColoredFormatter('%(color_levelname)s: %(color_msg)s'))
        self._logger.addHandler(cout)
        self._logger.trace = lambda msg, *args: self._logger._log(logging.TRACE, msg, args)
        # output to a log file
        if self._logfile is not None:
            ch = logging.FileHandler(self._logfile, mode = 'a')
            # debug informaiton and time is always written to the log file
            ch.setLevel(logging.DEBUG)
            ch.setFormatter(logging.Formatter('%(asctime)s: %(levelname)s: %(message)s'))
            self._logger.addHandler(ch)
    #
    # atribute logger
    #
    @property
    def logger(self):
        return self._logger
    #
    # attribute verbosity
    #
    def _set_verbosity(self, v):
        if v in [0, 1, 2, 3, 4]:
            self._verbosity = v
            # reset logger to appropriate logging level
            self._set_logger()
    #
    verbosity = property(lambda self: self._verbosity, _set_verbosity)
    #
    # attribute logfile
    #
    def _set_logfile(self, f):
        self._logfile = f
        # reset logger to include log file
        self._set_logger()
    #
    logfile = property(lambda self: self._logfile, _set_logfile)


# set up environment variable and a default logger
env = RuntimeEnvironments()
logger = env.logger


#
# String formatting
#
def getTermWidth():
    '''Get the width of current user terminal to properly wrap SoS
    output when well-formatted output is required.
    '''
    width = blessings.Terminal().width
    return 75 if width is None else width

class _DeHTMLParser(HTMLParser):
    '''This parser analyzes input text, removes HTML tags such as
    <p>, <br>, <ul>, <li> etc and returns properly formatted texts.
    '''
    def __init__(self):
        HTMLParser.__init__(self)
        self.__text = []

    def handle_data(self, data):
        text = data.strip()
        if len(text) > 0:
            text = re.sub('[ \t\r\n]+', ' ', text)
            self.__text.append(text + ' ')

    def handle_starttag(self, tag, attrs):
        if tag == 'p':
            self.__text.append('\n\n\n\n')
        elif tag == 'br':
            self.__text.append('\n\n')
        elif tag == 'ul':
            self.__text.append('')
        elif tag == 'li':
            self.__text.append('\n\n  * ')

    def handle_endtag(self, tag):
        if tag == 'ul':
            self.__text.append('\n\n')
        if tag == 'li':
            self.__text.append('\n\n')

    def handle_startendtag(self, tag, attrs):
        if tag == 'br':
            self.__text.append('\n\n')

    def text(self):
        return ''.join(self.__text).strip()

def dehtml(text):
    '''Remove HTML tag in input text and format the texts
    accordingly. '''
    try:
        parser = _DeHTMLParser()
        parser.feed(text)
        parser.close()
        return parser.text()
    except Exception as e:
        env.logger.warning('Failed to dehtml text: {}'.format(e))
        return text

# exception classes
class Error(Exception):
    '''Base class for SoS_ScriptParser exceptions.'''

    def _get_message(self):
        '''Getter for 'message'; needed only to override deprecation in
        BaseException.'''
        return self.__message

    def _set_message(self, value):
        '''Setter for 'message'; needed only to override deprecation in
        BaseException.'''
        self.__message = value

    # BaseException.message has been deprecated since Python 2.6.  To prevent
    # DeprecationWarning from popping up over this pre-existing attribute, use
    # a new property that takes lookup precedence.
    message = property(_get_message, _set_message)

    def __init__(self, msg=''):
        self.message = msg
        Exception.__init__(self, msg)

    def __repr__(self):
        return self.message

    __str__ = __repr__


def get_traceback():
    output = StringIO()
    exc_type, exc_value, exc_traceback = sys.exc_info()
    #print "*** print_tb:"
    traceback.print_tb(exc_traceback, limit=1, file=output)
    #print "*** print_exception:"
    traceback.print_exception(exc_type, exc_value, exc_traceback,
                              limit=5, file=output)
    result = output.getvalue()
    output.close()
    return result
    #print "*** print_exc:"
    #traceback.print_exc()
    #print "*** format_exc, first and last line:"
    #formatted_lines = traceback.format_exc().splitlines()
    #print formatted_lines[0]
    #print formatted_lines[-1]
    #print "*** format_exception:"
    #print repr(traceback.format_exception(exc_type, exc_value,
    #                                      exc_traceback))
    #print "*** extract_tb:"
    #print repr(traceback.extract_tb(exc_traceback))
    #print "*** format_tb:"
    #print repr(traceback.format_tb(exc_traceback))
    #print "*** tb_lineno:", exc_traceback.tb_lineno


def pickleable(obj):
    if isinstance(obj, (str, bool, int, float, complex, bytes)):
        return True
    if isinstance(obj, (types.ModuleType, WorkflowDict)):
        return False
    try:
        pickle.dumps(obj)
        return True
    except:
        return False

class ProgressBar:
    '''A text-based progress bar, it differs from regular progress bar in that
    1. it can start from the middle with init count
    '''
    def __init__(self, message, totalCount = None, disp=True, index=None):
        if not disp:
            self.update = self.empty
            self.curlUpdate = self.empty
            self.progress = self.empty
            self.outputProgress = self.empty
            self.done = self.empty
            self.main = ''
            self.finished = 0
            return
        self.index = index
        if self.index is not None:
            self.term = blessings.Terminal(stream=sys.stderr)
        self.main = message
        self.main_start_time = time.time()
        self.message = self.main
        # get terminal width
        self.term_width = getTermWidth()
        #
        # total count
        self.count = 0
        # total initial count
        self.init_count = self.count
        #
        self.finished = 0
        self.reset('', totalCount)

    def reset(self, msg='', totalCount = None):
        if msg:
            self.message = '{} - {}'.format(self.main, msg)
        self.finished += self.count
        self.count = 0
        self.totalCount = totalCount
        self.min_progress_count = None if self.totalCount is None else self.totalCount / 1000
        self.last_progress_count = 0
        self.start_time = None
        self.last_time = None
        self.outputProgress()

    def empty(self, *args, **kwargs):
        return

    def update(self, count):
        '''completed count jobs'''
        # do not update if the diferent is less than 0.1% of the total count.
        # this is to avoid excess of calling the time() function
        if self.totalCount is not None and (count - self.count) < self.min_progress_count:
            return
        self.count = count
        self.outputProgress()

    def curlUpdate(self, total, existing, upload_t, upload_d):
        '''Update called from pycurl'''
        self.count = existing
        self.totalCount = total
        self.outputProgress()

    def progress(self, count):
        self.last_progress_count += count
        if self.last_progress_count > self.min_progress_count:
            self.count += self.last_progress_count
            self.outputProgress()
            self.last_progress_count = 0

    def outputProgress(self):
        '''Output progress'''
        if not self.start_time:
            self.start_time = time.time()
            self.last_time = self.start_time
        cur_time = time.time()
        # stop update progress bar more than once per second.
        if self.count > 0 and self.count > self.init_count and \
            self.count != self.totalCount and cur_time - self.last_time < 1:
            return
        msg = ['', '', '', '', '', '', '']
        # message
        msg[0] = self.message + ':'
        self.last_time = cur_time
        second_elapsed = cur_time - self.start_time
        if second_elapsed < 0.0001 or self.count == 0:
            msg[4] = ''
        else:
            cps = (self.count - self.init_count) / second_elapsed
            # speed
            if cps > 1000000:
                msg[4] = ' {:.1f}M/s'.format(cps/1000000)
            elif cps > 1000:
                msg[4] = ' {:.1f}K/s'.format(cps/1000)
            elif cps > 0.05:
                msg[4] = ' {:.1f}/s'.format(cps)
            elif cps > 1e-6:
                msg[4] = ' {:.1f}s each'.format(1. / cps)
            else:
                msg[4] = ' 0.0/s'
        # estimated time left
        if self.totalCount:
            perc = min(1, float(self.count) / self.totalCount)
            init_perc = min(1, float(self.init_count) / self.totalCount)
            time_left = (second_elapsed / (perc - init_perc) * (1 - perc)) if perc > init_perc else 0
            msg[5] += ' in {}{}'.format('' if time_left < 86400 else '{} day{} '
                .format(int(time_left/86400), 's' if time_left > 172800 else ''),
                time.strftime('%H:%M:%S', time.gmtime(time_left)))
        # percentage / progress
        if self.count > 0:
            msg[3] = ' {:,}'.format(int(self.count))
            m3Len = len(msg[3])
        else:
            msg[3] = ' '
            m3Len = 1
        if self.totalCount:
            # percentage
            perc = min(1, float(self.count) / self.totalCount)
            msg[1] = ' {:5.1f}%'.format(perc * 100)
            width = self.term_width - len(msg[0]) - len(msg[1]) - m3Len - len(msg[4]) - len(msg[5])
            if width > 5:
                front = int(perc * (width - 4))
                back = width - 4 - front
                msg[2] = ' [{}>{}]'.format('=' * front, ' ' * back)
        else:
            width = self.term_width - len(msg[0]) - len(msg[1]) - m3Len - len(msg[4])
            msg[6] = ' '*width
        # use stderr to avoid messing up process output
        if self.index is None:
            sys.stderr.write('\r' + ''.join(msg))
        else:
            with self.term.location( 0, self.term.height - self.index - 1):
                sys.stderr.write('\r' + ''.join(msg))

    def done(self, done_msg=''):
        '''Finish, output a new line'''
        # if an message is given, display and quit.
        if self.totalCount and not done_msg:
            self.count = self.totalCount
        #
        msg = ['', '', '', '', '', '']
        # message
        msg[0] = self.main + ':'
        second_elapsed = time.time() - self.main_start_time
        cps = 0 if second_elapsed < 0.0001 else (self.finished + self.count) / second_elapsed
        # speed
        if cps > 1000000:
            msg[4] = ' {:.1f}M/s'.format(cps/1000000)
        elif cps > 1000:
            msg[4] = ' {:.1f}K/s'.format(cps/1000)
        elif cps > 0.05:
            msg[4] = ' {:.1f}/s'.format(cps)
        elif cps > 1e-6:
            msg[4] = ' {:.1f}s each'.format(1. / cps)
        else:
            msg[4] = ' 0.0/s'
        #
        msg[3] = ' {:,}'.format(self.finished + self.count)
        m3Len = len(msg[3])
        msg[5] += ' in {}{}'.format('' if second_elapsed < 86400 else '{} day{} '
            .format(int(second_elapsed/86400), 's' if second_elapsed > 172800 else ''),
                time.strftime('%H:%M:%S', time.gmtime(second_elapsed)))
        # percentage / progress
        if self.totalCount:
            # percentage
            msg[1] = ' 100%'
            width = self.term_width - len(msg[0]) - len(msg[1]) - m3Len - len(msg[4]) - len(msg[5])
            if width > 4:
                front = int(width - 3)
                msg[2] = ' [{}]'.format('=' * front)
        #
        if done_msg:
            msg[0] = done_msg
            msg[1] = ''
            msg[2] = ''
            msg[3] = ''
            msg[4] = ''
            msg[5] = ''
        if self.index is None:
            sys.stderr.write('\r' + ''.join(msg) + '\n')
            sys.stderr.flush()
        else:
            with self.term.location(0, self.term.height - self.index - 1):
                sys.stderr.write('\r' + ''.join(msg))
                sys.stderr.flush()


class frozendict(dict):
    '''A fronzen dictionary that disallow changing of its elements
    Copied from http://code.activestate.com/recipes/414283/
    '''
    def _blocked_attribute(obj):
        raise RuntimeError("Cannot modify a readonly dictionary.")
    _blocked_attribute = property(_blocked_attribute)

    __delitem__ = __setitem__ = clear = _blocked_attribute
    pop = popitem = setdefault = update = _blocked_attribute

    def __new__(cls, *args):
        new = dict.__new__(cls)
        dict.__init__(new, *args)
        return new

    def __init__(self, *args):
        pass

    def __hash__(self):
        try:
            return self._cached_hash
        except AttributeError:
            h = self._cached_hash = hash(tuple(sorted(self.items())))
            return h

    def __getattr__(self, key):
        return dict.__getitem__(self, key)

    def __setattr__(self, key, value):
        raise RuntimeError('Cannot modify a readonly dictionary')

    def __repr__(self):
        return "frozendict(%s)" % dict.__repr__(self)

#
# A utility function that returns output of a command
def get_output(cmd, show_command=False, prompt='$ '):
    try:
        output = subprocess.check_output(cmd, shell=True).decode()
    except subprocess.CalledProcessError as e:
        if e.output.decode():
            env.logger.error(e.output.decode())
        raise RuntimeError(e)
    if show_command:
        return '{}{}\n{}'.format(prompt, cmd, output)
    else:
        return output

#
# search a path and locate script and other files
#
def locate_script(filename, start=''):
    #
    attemp = os.path.expanduser(filename)
    if os.path.isfile(attemp):
        return ('', attemp)
    #
    token = urllib.parse.urlparse(filename)
    # if no scheme or netloc, the URL is not acceptable
    if all([getattr(token, qualifying_attr) for qualifying_attr in  ('scheme', 'netloc')]):
        try:
            local_filename, headers = urllib.request.urlretrieve(filename)
            with open(local_filename) as script:
                content = script.read()
            #
            return (content, filename)
        except Exception as e:
            env.logger.error(e)
            raise ValueError('Failed to open {}'.format(filename))
    #
    # a search path
    pathes = [start]
    sos_config_file = os.path.expanduser('~/.sos/config.yaml')
    if os.path.isfile(sos_config_file):
        try:
            with open(sos_config_file) as config:
                cfg = yaml.safe_load(config)
        except Exception as e:
            raise RuntimeError('Failed to parse global sos config file {}, is it in JSON format?'.format(sos_config_file))
        #
        pathes.extend(cfg.get('sos_path', []))
    #
    sos_config_file = '.sos/config.yaml'
    if os.path.isfile(sos_config_file):
        try:
            with open(sos_config_file) as config:
                cfg = yaml.safe_load(config)
        except Exception as e:
            raise RuntimeError('Failed to parse global sos config file {}, is it in YAML/JSON format?'.format(sos_config_file))
        #
        pathes.extend(cfg.get('sos_path', []))
    #
    for path in pathes:
        if not path:
            continue
        attemp = os.path.join(os.path.expanduser(path), os.path.expanduser(filename))
        if os.path.isfile(attemp):
            return ('', attemp)
        # is it an URL?
        token = urllib.parse.urlparse(path)
        # if no scheme or netloc, the URL is not acceptable
        if all([getattr(token, qualifying_attr) for qualifying_attr in  ('scheme', 'netloc')]):
            url = path + ('' if path.endswith('/') else '/') + filename
            try:
                local_filename, headers = urllib.request.urlretrieve(url)
                with open(local_filename) as script:
                    content = script.read()
                return content, url
            except Exception as e:
                pass
    #
    raise ValueError('Failed to locate {}'.format(filename))

def text_repr(text):
    """Rich repr for ``text`` returning unicode, triple quoted if ``multiline``.
    """
    if text.count('\n') <= 1:
        return repr(text)
    elif "'''" not in text and not text.endswith("'"):
        return "r'''" + text + "'''"
    elif '"""' not in text and not text.endswith('"'):
        return 'r"""' + text + '"""'
    else:
        # cannot really use triple quote in this case
        return repr(text)

def natural_keys(text):
    '''
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    '''
    return [ int(c) if c.isdigit() else c for c in re.split('(\d+)', text) ]

def transcribe(text, action=None):
    if action is not None:
        text = '{}:\n{}'.format(action, '    ' + text.replace('\n', '\n    ') + '\n')
    if '__transcript__' not in env.sos_dict:
        raise RuntimeError('Transcript not defined')
    if env.sos_dict['__transcript__'] is None:
        return
    if env.sos_dict['__transcript__'] == '__STDERR__':
        sys.stderr.write(text)
    else:
        with open(env.sos_dict['__transcript__'], 'a') as trans:
            trans.write(text)
