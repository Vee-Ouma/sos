#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import argparse
import ast
import os
import sys
import datetime
import pkg_resources

script_help = '''A SoS script that defines one or more workflows, in format
    .sos or .ipynb. The script can be a filename or a URL from which the
    content of a SoS will be read. If a valid file cannot be located or
    downloaded, SoS will search for the script, with specified name, and
    with added extension .sos and .ipynb, in a search path specified by
    variable `sos_path` defined in the global SoS configuration file
    (~/.sos/config.yml).'''
workflow_spec = '''Name of the workflow to execute. This option can be
    ignored if the script defines a default workflow (with no name or with
    name `default`) or defines only a single workflow. A subworkflow or a
    combined workflow can also be specified, where a subworkflow executes a
    subset of workflow (`name_steps` where `steps` can be `n` (a step `n`),
    `:n` (up to step `n`), `n:m` (from step `n` to `m`), and `n:` (from step
    `n`)), and a combined workflow executes to multiple (sub)workflows
    combined by `+` (e.g. `A_0+B+C`).'''
workflow_options = '''Arbitrary parameters defined by the [parameters] step
    of the script, and [parameters] steps of other scripts if nested workflows
    are defined in other SoS files (option `source`). The name, default and
    type of the parameters are specified in the script. Single value parameters
    should be passed using option `--name value` and multi-value parameters
    should be passed using option `--name value1 value2`. '''
transcript_help = '''Name of a file that records the execution transcript of
    the script. The transcript will be recorded in dryrun and run mode but
    might differ in content because of dynamic input and output of scripts.
    If the option is specified wiht no value, the transcript will be written
    to standard error output.'''
bindir_help = '''Extra directories in which SoS will look for executables before
    standard $PATH. This option essentially prefix $PATH with these directories.
    Note that the default value '~/.sos/bin' is by convention a default
    directory for commands that are installed by SoS. You can use option '-b'
    without value to disallow commands under ~/.sos/bin.'''

#
# subcommand install
#
# def get_install_parser(desc_only=False):
#     parser = argparse.ArgumentParser('install',
#         description='''Install various component to the system''')
#     parser.short_description = '''Install various components to the system'''
#     if desc_only:
#         return parser
#     parser.set_defaults(func=cmd_install)
#     subparsers = parser.add_subparsers(title='installers', dest='installer_name')
#     for entrypoint in pkg_resources.iter_entry_points(group='sos_installers'):
#         try:
#             name = entrypoint.name
#             if not name.endswith('.parser'):
#                 continue
#             item = name.rsplit('.',1)[0]
#             subparser = add_sub_parser(subparsers, entrypoint.load()(), name=item)
#         except Exception as e:
#             print('Failed to load installer {}: {}'.format(entrypoint.name, e))
#     return parser
#
#
# def cmd_install(args, unknown_args):
#     from .utils import env, get_traceback
#     for entrypoint in pkg_resources.iter_entry_points(group='sos_installers'):
#         try:
#             if entrypoint.name == args.installer_name + '.func':
#                 func = entrypoint.load()
#                 func(args)
#         except Exception as e:
#             # if no other parameter, with option list all
#             if args.verbosity and args.verbosity > 2:
#                 sys.stderr.write(get_traceback())
#             env.logger.error('Failed to execute installer {}: {}'.format(entrypoint.name.rsplit('.', 1)[0], e))
#             sys.exit(1)
#
#
# subcommand convert
#


def get_convert_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'convert',
        description='''Converts .sos to various formats including
            .html for web display, to jupyter notebook (.ipynb), and to terminal
            for syntax highlighted viewing on terminal. It also allows converting
            from jupyter notebook (.ipynb) to sos script (.sos).''',
        epilog='''Extra command line argument could be specified to customize
            the style of html, markdown, and terminal output. ''',
    )
    parser.short_description = '''Convert between .sos, .ipynb and other formats'''
    if desc_only:
        return parser
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_convert)
    subparsers = parser.add_subparsers(
        title='converters (name of converter is not needed from command line)',
        dest='converter_name')
    for entrypoint in pkg_resources.iter_entry_points(group='sos_converters'):
        try:
            name = entrypoint.name
            if not name.endswith('.parser'):
                continue
            f_format, t_format = name.rsplit('.', 1)[0].split('-')
            subparser = add_sub_parser(
                subparsers,
                entrypoint.load()(),
                name='{}-{}'.format(f_format, t_format))
            subparser.add_argument(
                'from_file',
                metavar='FROM',
                nargs='?',
                help='''File to be converted.''')
            subparser.add_argument(
                'to_file',
                metavar='TO',
                nargs='?',
                help='''File to convert to, default to standard output if no file
                    name is given.''')
            subparser.add_argument(
                '-t',
                '--to',
                dest='__to_format__',
                metavar='TO_FORMAT',
                help='''Destination file format, which is usually determined from
                    extension of `to_file` filename, but is needed if `to_file` is
                    unspecified.''')
        except Exception as e:
            print('Failed to load converter {}: {}'.format(entrypoint.name, e))
    return parser


def get_converter_formats(argv):
    if len(argv) == 1 and '-' in argv[0] and '.' not in argv[0]:
        return argv[0].split('-', 1)
    parser = argparse.ArgumentParser('convert')
    parser.add_argument('from_file', nargs='?')
    parser.add_argument('to_file', nargs='?')
    parser.add_argument('-t', '--to', dest='__to_format__')
    args, _ = parser.parse_known_args(argv)
    from_format = args.from_file[1:] if args.from_file.startswith('.') and args.from_file.count('.') == 1 \
        else os.path.splitext(args.from_file)[-1][1:]
    if not from_format:
        from_format = 'sos'
    if args.__to_format__:
        to_format = args.__to_format__
    elif args.to_file:
        to_format = args.to_file[1:] if args.to_file.startswith('.') and args.to_file.count('.') == 1 \
            else os.path.splitext(args.to_file)[-1][1:]
    else:
        return None, None
    return from_format, to_format


def print_converter_help():
    from_format, to_format = get_converter_formats(
        [x for x in sys.argv[2:] if x != '-h'])
    if from_format is None or to_format is None:
        return
    for entrypoint in pkg_resources.iter_entry_points(group='sos_converters'):
        try:
            name = entrypoint.name
            if not name.endswith('.parser'):
                continue
            f_format, t_format = name.rsplit('.', 1)[0].split('-')
            if from_format != f_format or to_format != t_format:
                continue
            parser = entrypoint.load()()
            sys.exit(parser.print_help())
        except Exception as e:
            sys.exit('Failed to load converter {}: {}'.format(
                entrypoint.name, e))


def cmd_convert(args, unknown_args):
    from .utils import env, get_traceback
    for entrypoint in pkg_resources.iter_entry_points(group='sos_converters'):
        try:
            if entrypoint.name == args.converter_name + '.func':
                func = entrypoint.load()
                func(args.from_file, args.to_file, args, unknown_args)
        except Exception as e:
            # if no other parameter, with option list all
            if args.verbosity and args.verbosity > 2:
                sys.stderr.write(get_traceback())
            env.logger.error('Failed to execute converter {}: {}'.format(
                entrypoint.name.rsplit('.', 1)[0], e))
            sys.exit(1)


#
# subcommand run
#


def get_run_parser(interactive=False, with_workflow=True, desc_only=False):
    parser = argparse.ArgumentParser(
        prog='run',
        description='Execute default or specified workflow defined in script',
        epilog=workflow_options)
    parser.short_description = 'Execute default or specified workflow in script'
    if desc_only:
        return parser
    if not interactive:
        parser.add_argument('script', metavar='SCRIPT', help=script_help)
    if with_workflow:
        parser.add_argument(
            'workflow', metavar='WORKFLOW', nargs='?', help=workflow_spec)
    parser.add_argument(
        '-j',
        type=int,
        metavar='JOBS',
        dest='__max_procs__',
        default=min(max(os.cpu_count() // 2, 1), 8),
        help='''Maximum number of worker processes for the execution of steps in
            a workflow and substeps in a step (with input option concurrent), default to half of
            number of CPUs, or 8, whichever is smaller''')
    parser.add_argument(
        '-J',
        type=int,
        metavar='EXTERNAL_JOBS',
        dest='__max_running_jobs__',
        help='''Maximum number of externally running tasks. This option
            overrides option "max_running_jobs" of a task queue (option -q)
            so that you can, for example, submit one job at a time (with
            -J 1) to test the task queue.''')
    parser.add_argument(
        '-c',
        dest='__config__',
        metavar='CONFIG_FILE',
        help='''A configuration file in the format of YAML/JSON. The content
            of the configuration file will be available as a dictionary
            CONF in the SoS script being executed.''')
    parser.add_argument(
        '-t',
        dest='__targets__',
        metavar='FILE',
        default=[],
        nargs='+',
        help='''One of more files or names of named outputs that
            will be the target of execution. If specified, SoS will execute
            only part of a workflow or multiple workflows or auxiliary steps
            to generate specified targets.''')
    parser.add_argument(
        '-b',
        dest='__bin_dirs__',
        nargs='*',
        metavar='BIN_DIR',
        default=['~/.sos/bin'],
        help=bindir_help)
    parser.add_argument(
        '-q',
        dest='__queue__',
        default="",
        metavar='QUEUE',
        help='''host (server) or job queues to execute all tasks in the
            workflow. The queue can be defined in global or local sos
            configuration file, or a file specified by option  --config. A host is
            assumed to be a remote machine with process type if no configuration
            is found. If a value "None" is specified, tasks are executed as part of
            regular step processes unless task-specific queues are specified.'''
    )
    parser.add_argument(
        '-r',
        dest='__remote__',
        metavar='HOST',
        nargs='?',
        const='',
        help='''Execute the workflow in specified remote host, which should
            be defined under key host of sos configuration files (preferrably
            in ~/.sos/hosts.yml). This option basically copy the workflow
            to remote host and invoke sos command there. No path translation
            and input/output file synchronization will be performed before or
            after the execution of the workflow.''')
    # parser.add_argument('-t', dest='__transcript__', nargs='?',
    #    metavar='TRANSCRIPT', const='__STDERR__', help=transcript_help)
    runmode = parser.add_argument_group(
        title='Run mode options',
        description='''Control how sos scirpt is executed.''')
    runmode.add_argument(
        '-n',
        action='store_true',
        dest='dryrun',
        help='''Execute a workflow in dryrun mode. Please check command
        sos dryrun for details of the dryrun mode.''')
    runmode.add_argument(
        '-s',
        choices=['default', 'ignore', 'force', 'build', 'assert', 'skip', 'distributed'],
        default='default',
        metavar='SIGMODE',
        dest='__sig_mode__',
        help='''How runtime signature would be handled, which can be "default"
            (save and use signature, default mode in batch mode), "ignore"
            (ignore runtime signature, default mode in interactive mode),
            "force" (ignore existing signature and overwrite them while
            executing the workflow), "build" (build new or overwrite
            existing signature from existing environment and output files),
            and "assert" for validating existing files against their signatures.
            "skip" and "distributed" are two experimental modes with "skip" for
            bypassing substep as long as step output exists and later than input
            files and "distributed" for sending tasks to subworkers for signature
            validation. Please refer to online documentation for details about
            the use of runtime signatures.''')
    runmode.add_argument(
        '-T',
        action='store_true',
        dest='trace_existing',
        help='''Trace existing targets and re-execute the steps that generate
            them to make sure that the targets are current.''')
    runmode.add_argument(
        '-k',
        action='store_true',
        dest='keep_going',
        help='''Keep completing the DAG even after some step has failed. By
            default, SoS will stop executing the DAG (but wait until all
            running jobs are completed) when an error happens. With this
            option, SoS will mark a branch of DAG as failed but still tries
            to complete other parts of the DAG.''')
    # run in tapping mode etc
    runmode.add_argument(
        '-m', nargs='+', dest='exec_mode', help=argparse.SUPPRESS)
    output = parser.add_argument_group(
        title='Output options', description='''Output of workflow''')
    output.add_argument(
        '-d',
        nargs='?',
        default='',
        metavar='DAG',
        dest='__dag__',
        help='''Output Direct Acyclic Graph (DAGs) in graphiviz .dot format.
            Because DAG and status of nodes will change during the execution of
            workflow, multiple DAGs will be written to the specified file with
            names {workflow}_1, {workflow}_2 etc. The dot file would be named
            {script_name}_{timestamp}.dot unless a separate filename is specified.'''
    )
    output.add_argument(
        '-p',
        nargs='?',
        default='',
        metavar='REPORT',
        dest='__report__',
        help='''Output a report that summarizes the execution of the
            workflow after the completion of the execution. This includes command line,
            steps executed, tasks executed, CPU/memory of tasks, and DAG if option -d
            is also specified. The report will by be named {script_name}_{timestamp}.html
            unless a separate filename is specified.''')
    output.add_argument(
        '-v',
        dest='verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_run)
    return parser


def cmd_run(args, workflow_args):
    #import multiprocessing as mp
    # #562, #558, #493
    #
    # if sys.platform != 'win32':
    #    mp.set_start_method('forkserver')

    from .utils import env, get_traceback, load_config_files
    from .parser import SoS_Script

    if args.__remote__ is not None:
        # if executing on a remote host...
        from .hosts import Host
        load_config_files(args.__config__)
        host = Host(args.__remote__)
        from .utils import remove_arg
        #
        # copy script to remote host...
        host.send_to_host(args.script)

        argv = remove_arg(sys.argv, '-r')
        # -c only point to local config file.
        argv = remove_arg(argv, '-c')
        # remove --slave mode because the master cannot reach remote slave
        argv = remove_arg(argv, '-m')
        # replace absolute path with relative one because remote sos might have
        # a different path.
        if os.path.basename(argv[0]) == 'sos':
            argv[0] = 'sos'
        elif os.path.basename(argv[0]) == 'sos-runner':
            argv[0] = 'sos-runner'
        # execute the command on remote host
        sys.exit(host._host_agent.check_call(argv, under_workdir=True))

    # '' means no -d
    dt = datetime.datetime.now().strftime('%m%d%y_%H%M')
    if args.__dag__ is None:
        args.__dag__ = f'{os.path.splitext(args.script)[0]}_{dt}.dot'
    elif args.__dag__ == '':
        args.__dag__ = None

    if args.__report__ is None:
        args.__report__ = f'{os.path.splitext(args.script)[0]}_{dt}.html'
    elif args.__report__ == '':
        args.__report__ = None
    env.verbosity = args.verbosity

    if args.__report__ and args.__dag__:
        try:
            import graphviz
            import PIL
            import imageio
            assert graphviz
            assert PIL
            assert imageio
        except ImportError as e:
            raise RuntimeError(
                f'Python packages graphviz, pillow, and imageio are required for the generation of DAG animation in workflow report (options -p with -d): {e}'
            )

        import shutil
        if not shutil.which('dot'):
            raise RuntimeError(
                f'Command dot from package graphviz is required for the generation of DAG animation in workflow report (options -p with -d)'
            )

    from .workflow_executor import Base_Executor

    if args.__bin_dirs__:
        for d in args.__bin_dirs__:
            if d == '~/.sos/bin' and not os.path.isdir(os.path.expanduser(d)):
                os.makedirs(os.path.expanduser(d), exist_ok=True)
            elif not os.path.isdir(os.path.expanduser(d)):
                raise ValueError('directory does not exist: {}'.format(d))
        os.environ['PATH'] = os.pathsep.join([
            os.path.expanduser(x) for x in args.__bin_dirs__
        ]) + os.pathsep + os.environ['PATH']

    try:
        # workflow args has to be in the format of --arg, not positional, not -a
        if workflow_args and not workflow_args[0].startswith('--'):
            raise ValueError("Unrecognized command line option {}".format(
                ' '.join(workflow_args)))
        script = SoS_Script(filename=args.script)
        workflow = script.workflow(
            args.workflow, use_default=not args.__targets__)
        config = {
            'config_file': args.__config__,
            'output_dag': args.__dag__,
            'output_report': args.__report__,
            'default_queue': args.__queue__,
            'max_procs': args.__max_procs__,
            'max_running_jobs': args.__max_running_jobs__,
            'sig_mode': 'ignore' if args.dryrun else args.__sig_mode__,
            # when being tapped by sos notebook, we suppose it is in interactive mode
            'run_mode': 'dryrun' if args.dryrun else ('interactive' if args.exec_mode else 'run'),
            'verbosity': args.verbosity,
            # for infomration only
            'workdir': os.getcwd(),
            'script': args.script,
            'workflow': args.workflow,
            'targets': args.__targets__,
            'bin_dirs': args.__bin_dirs__,
            'workflow_args': workflow_args,
            'trace_existing': args.trace_existing,
            'keep_going': args.keep_going,
            # tapping etc
            'exec_mode': args.exec_mode
        }
        if args.exec_mode:
            if args.exec_mode[0] != 'tapping' or len(args.exec_mode) == 1:
                raise ValueError(
                    f'Unsupported exec_mode (option -m). {args.exec_mode} provided'
                )
            if args.exec_mode[1] != 'slave':
                raise ValueError(
                    f'Unsupported exec_mode (option -m). {args.exec_mode} provided'
                )
            if len(args.exec_mode) != 6:
                raise ValueError(
                    f'Unsupported exec_mode (option -m). {args.exec_mode} provided'
                )
            try:
                config['slave_id'] = args.exec_mode[2]
                config['sockets'] = {
                    'tapping_logging': int(args.exec_mode[3]),
                    'tapping_listener': int(args.exec_mode[4]),
                    'tapping_controller': int(args.exec_mode[5]),
                }
            except Exception as e:
                raise ValueError(
                    f'Unsupported exec_mode (option -m). {args.exec_mode} provided: {e}'
                )
            #env.logger.debug(f'Process being tapped as slave {config["slave_id"]} at {config["sockets"]["tapping_logging"]} (logger) and {config["sockets"]["tapping_controller"]} (controller)')
            config['exec_mode'] = args.exec_mode[1]

        executor = Base_Executor(workflow, args=workflow_args, config=config)
        # start controller
        executor.run(args.__targets__, mode=config['run_mode'])
    except Exception as e:
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


#
# subcommand dryrun
#


def get_dryrun_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'dryrun',
        description='''Execute workflow in dryrun mode. This mode is identical
        to run mode except that 1). Actions might behavior differently. In
        particular, script-running steps would print instead of execute script.
        2). Steps will generate empty output files if specified output do not
        exist after execution. 3). Signature mode is set to ignore. 4). Option
        -q is ignored so all tasks are executed locally. 5). Tasks are generated
        but not executed.''',
        epilog=workflow_options)
    parser.short_description = '''Execute workflow in dryrun mode'''
    if desc_only:
        return parser
    parser.add_argument('script', metavar='SCRIPT', help=script_help)
    parser.add_argument(
        'workflow', metavar='WORKFLOW', nargs='?', help=workflow_spec)
    parser.add_argument(
        '-c',
        dest='__config__',
        metavar='CONFIG_FILE',
        help='''A configuration file in the format of YAML/JSON. The content
            of the configuration file will be available as a dictionary
            CONF in the SoS script being executed.''')
    parser.add_argument(
        '-t',
        dest='__targets__',
        metavar='FILES',
        default=[],
        nargs='+',
        help='''One of more files or alias of other targets that
            will be the target of execution. If specified, SoS will execute
            only part of a workflow or multiple workflows or auxiliary steps
            to generate specified targets. ''')
    parser.add_argument(
        '-q',
        dest='__queue__',
        default='*',
        metavar='QUEUE',
        help='''host (server) or job queues to execute all tasks in the
            workflow. The queue can be defined in global or local sos
            configuration file, or a file specified by option  --config. A host is
            assumed to be a remote machine with process type if no configuration
            is found. ''')
    runmode = parser.add_argument_group(
        title='Run mode options',
        description='''Control how sos scirpt is executed.''')
    runmode.add_argument(
        '-T',
        action='store_true',
        dest='trace_existing',
        help='''Trace existing targets and re-execute the steps that generate
            them to make sure that the targets are current.''')
    output = parser.add_argument_group(
        title='Output options', description='''Output of workflow''')
    output.add_argument(
        '-d',
        nargs='?',
        default='',
        metavar='DAG',
        dest='__dag__',
        help='''Output Direct Acyclic Graph (DAGs) in graphiviz .dot format. An
            exntesion of ".dot" would be added automatically. Because DAG could
            change during the execution of workflow, multiple DAGs could be
            outputed with names $FILE_1.dot, $FILE_2.dot. If this option is
            specified without a name, the DAG would be wrritten to the standard
            output.''')
    output.add_argument(
        '-p',
        nargs='?',
        default='',
        metavar='REPORT',
        dest='__report__',
        help='''Output a report that summarizes the execution of the
            workflow after the completion of the execution. This includes command line,
            steps executed, tasks executed, CPU/memory of tasks, and DAG if option -d
            is also specified. The report will by be named {script_name}_{timestamp}.html
            unless a separate filename is specified.''')
    output.add_argument(
        '-v',
        dest='verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2), debug (3) and trace (4)
            information to standard output (default to 2).''')
    parser.set_defaults(func=cmd_dryrun)
    return parser


def cmd_dryrun(args, workflow_args):
    args.__sig_mode__ = 'ignore'
    args.__max_procs__ = 1
    args.__max_running_jobs__ = 1
    args.dryrun = True
    args.__bin_dirs__ = []
    args.__remote__ = None
    args.exec_mode = None
    args.keep_going = False
    cmd_run(args, workflow_args)


#
# subcommand push
#


def get_push_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'push',
        description='''Push local files or directory to a remote host''')
    if desc_only:
        return parser
    parser.add_argument(
        'items',
        nargs='+',
        help='''Files or directories to be sent
        to remote host. The location of remote files are determined by "path_map"
        determined by "paths" definitions of local and remote hosts.''')
    parser.add_argument(
        '-t',
        '--to',
        dest='host',
        help='''Remote host to which the files will be sent, which should
        be one of the hosts defined in sos configuration files.''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_push)
    return parser


def cmd_push(args, workflow_args):
    from .utils import env, load_config_files
    from .hosts import Host
    env.verbosity = args.verbosity
    load_config_files(args.config)
    try:
        host = Host(args.host)
        #
        sent = host.send_to_host(args.items)
        #
        print('{} item{} sent:\n{}'.format(
            len(sent), ' is' if len(sent) <= 1 else 's are', '\n'.join(
                ['{} => {}'.format(x, sent[x]) for x in sorted(sent.keys())])))
    except Exception as e:
        from .utils import get_traceback
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


#
# subcommand pull
#


def get_pull_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'pull',
        description='''Pull files or directories from remote host to local host'''
    )
    if desc_only:
        return parser
    parser.add_argument(
        'items',
        nargs='+',
        help='''Files or directories to be
        retrieved from remote host. The files should be relative to local file
        system. The files to retrieve are determined by "path_map"
        determined by "paths" definitions of local and remote hosts.''')
    parser.add_argument(
        '-f',
        '--from',
        dest='host',
        help='''Remote host to which the files will be sent, which should
        be one of the hosts defined in sos configuration files.''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_pull)
    return parser


def cmd_pull(args, workflow_args):
    from .utils import env, load_config_files
    from .hosts import Host
    env.verbosity = args.verbosity
    load_config_files(args.config)
    try:
        host = Host(args.host)
        #
        received = host.receive_from_host(args.items)
        #
        print('{} item{} received:\n{}'.format(
            len(received), ' is' if len(received) <= 1 else 's are', '\n'.join([
                '{} <= {}'.format(x, received[x])
                for x in sorted(received.keys())
            ])))
    except Exception as e:
        from .utils import get_traceback
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


#
# subcommand remote
#


def get_remote_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'remote', description='''Listing and testing remote configurations''')
    if desc_only:
        return parser
    parser.add_argument(
        'action',
        choices=[
            'list', 'status', 'setup', 'test', 'login', 'push', 'pull', 'run'
        ],
        help='''List (list), check status of tasks (status), setup public-key
                         authentication (setup), test configuration (test), login (login), push files
                         to one or more remote hosts (push), pull files from a remote host,
                         or execute command (run) on one or all or specified remote hosts'''
    )
    parser.add_argument(
        'hosts',
        nargs='*',
        metavar='hosts',
        help='''Hosts to be checked or tested. All hosts defined in SoS configurations will be
        included if unspecified. As a special case for "sos remote setup", an address is acceptable even if it
        is defined in configuration file.''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-p',
        '--password',
        help='''Password used to copy public key to remote hosts. You will be prompted
            for a password if a password is needed and is not passed from command line. The same password will be used for
            all specified hosts so you will need to use separate setup commands for hosts with different passwords.'''
    )
    parser.add_argument(
        '--files',
        nargs='*',
        help='''files or directories to be push or pulled for action "push" or "pull"'''
    )
    parser.add_argument(
        '--cmd', nargs='*', help='''commands to be executed by action "run"''')
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_remote)
    return parser


def cmd_remote(args, workflow_args):
    from .utils import env, load_config_files
    cfg = load_config_files(args.config)
    try:
        if args.action == 'list':
            from .hosts import list_queues
            list_queues(cfg, args.hosts, args.verbosity)
        elif args.action == 'status':
            from .hosts import status_of_queues
            status_of_queues(cfg, args.hosts, args.verbosity)
        elif args.action == 'setup':
            from .hosts import setup_remote_access
            setup_remote_access(cfg, args.hosts, args.password, args.verbosity)
        elif args.action == 'test':
            from .hosts import test_queues
            test_queues(cfg, args.hosts, args.verbosity)
        elif args.action == 'login':
            from .hosts import login_host
            if not args.hosts:
                raise ValueError('Please specify a host to login')
            if len(args.hosts) > 1:
                raise ValueError(
                    f'Please specify only one host to login. {args.hosts} provided.'
                )
            login_host(cfg, args.hosts[0])
        elif args.action == 'run':
            if not args.cmd:
                raise ValueError(
                    'Please specify a command to execute with option --cmd')
            from .hosts import run_command_on_hosts
            run_command_on_hosts(cfg, args.hosts, args.cmd, args.verbosity)
        elif args.action == 'push':
            if not args.files:
                raise ValueError(
                    'Please specify files to push to remote host with option --files'
                )
            from .hosts import push_to_hosts
            push_to_hosts(cfg, args.hosts, args.files, args.verbosity)
        elif args.action == 'pull':
            if not args.files:
                raise ValueError(
                    'Please specify files to pull from remote host with option --files'
                )
            from .hosts import pull_from_host
            pull_from_host(cfg, args.hosts, args.files, args.verbosity)
        else:
            raise ValueError(
                "Unacceptable remote action. Use command 'sos remote -h' to check allowable actions."
            )
    except Exception as e:
        from .utils import get_traceback
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


#
# command preview
#


def get_preview_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        prog='preview',
        description='''Preview files, sos variables, or expressions in the
            side panel, or notebook if side panel is not opened, unless
            options --panel or --notebook is specified.''')
    parser.short_description = '''Preview files on local or remote host'''
    if desc_only:
        return parser
    parser.add_argument(
        'items',
        nargs='*',
        help='''Filename, variable name, or expression. Wildcard characters
            such as '*' and '?' are allowed for filenames.''')
    # this option is currently hidden
    parser.add_argument(
        '-s',
        '--style',
        choices=['table', 'scatterplot', 'png'],
        help='''Option for preview file or variable, which by default is "table"
        for Pandas DataFrame. The %%preview magic also accepts arbitrary additional
        keyword arguments, which would be interpreted by individual style. Passing
        '-h' with '--style' would display the usage information of particular
        style.''')
    parser.add_argument(
        '-r',
        '--host',
        dest='host',
        metavar='HOST',
        help='''Preview files on specified remote host, which should
        be one of the hosts defined in sos configuration files.''')
    parser.add_argument('--html', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(4),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_preview)
    return parser


def preview_file(previewers, filename, style=None):
    from .utils import pretty_size
    from IPython.core.display import HTML
    msg = []
    if not os.path.isfile(filename):
        msg.append([
            'stream', {
                'name': 'stderr',
                'text': '\n> ' + filename + ' does not exist'
            }
        ])
        return msg
    msg.append([
        'display_data', {
            'metadata': {},
            'data': {
                'text/plain':
                    '\n> {} ({}):'.format(
                        filename, pretty_size(os.path.getsize(filename))),
                'text/html':
                    HTML('<div class="sos_hint">> {} ({}):</div>'.format(
                        filename, pretty_size(os.path.getsize(filename)))).data,
            }
        }
    ])
    previewer_func = None
    # lazy import of previewers
    import fnmatch
    for x, y, _ in previewers:
        if isinstance(x, str):
            if fnmatch.fnmatch(os.path.basename(filename), x):
                # we load entrypoint only before it is used. This is to avoid
                # loading previewers that require additional external modules
                # we can cache the loaded function but there does not seem to be
                # a strong performance need for this.
                previewer_func = y.load()
                break
        else:
            # it should be a function
            try:
                if x(filename):
                    try:
                        previewer_func = y.load()
                    except Exception as e:
                        msg.append([
                            'stream', {
                                'name':
                                    'stderr',
                                'text':
                                    'Failed to load previewer {}: {}'.format(
                                        y, e)
                            }
                        ])
                        continue
                    break
            except Exception as e:
                msg.append(['stream', {'name': 'stderr', 'text': str(e)}])
                continue
    #
    # if no previewer can be found
    if previewer_func is None:
        return msg
    try:
        result = previewer_func(filename, None, style)
        if not result:
            return msg
        if isinstance(result, str):
            msg.append(['stream', {'name': 'stdout', 'text': result}])
        elif isinstance(result, dict):
            msg.append([
                'display_data', {
                    'source': filename,
                    'data': result,
                    'metadata': {}
                }
            ])
        elif isinstance(result, (list, tuple)) and len(result) == 2:
            msg.append([
                'display_data', {
                    'source': filename,
                    'data': result[0],
                    'metadata': result[1]
                }
            ])
        else:
            msg.append([
                'stream', {
                    'name': 'stderr',
                    'text': 'Unrecognized preview content: {}'.format(result)
                }
            ])
    except Exception as e:
        msg.append([
            'stream', {
                'name': 'stderr',
                'text': 'Failed to preview {}: {}'.format(filename, e)
            }
        ])
    return msg


def cmd_preview(args, unknown_args):
    from .utils import env, load_config_files
    from .hosts import Host
    load_config_files(args.config)
    env.verbosity = args.verbosity
    if args.host:
        # remote host?
        host = Host(args.host, start_engine=False)
        rargs = ['sos', 'preview'] + args.items + ['--html']
        if args.style:
            rargs += ['-s', args.style] + unknown_args
        if 'GENERAL' in env.config['SOS_DEBUG'] or 'ALL' in env.config['SOS_DEBUG']:
            env.log_to_file('GENERAL', 'Running "{}"'.format(' '.join(rargs)))
        msgs = eval(host._host_agent.check_output(rargs, under_workdir=True))
    else:
        from .preview import get_previewers
        previewers = get_previewers()
        msgs = []
        style = {
            'style': args.style,
            'options': unknown_args
        } if args.style or unknown_args else None
        for filename in args.items:
            msgs.extend(preview_file(previewers, filename, style))
    if args.html:
        print(msgs)
    else:
        from .utils import colorstr
        for msg in msgs:
            if msg[0] == 'stream':
                if msg[1]['name'] == 'stdout':
                    print(msg[1]['text'])
                else:
                    print(colorstr(msg[1]['text'], 'PURPLE'))
            elif msg[0] == 'display_data':
                if 'text/plain' in msg[1]['data']:
                    print(msg[1]['data']['text/plain'])
                elif 'text/html' in msg[1]['data']:
                    print(msg[1]['data']['text/html'])
                else:
                    print('BINARY DATA of type {}'.format(', '.join(
                        msg[1]['data'].keys())))
            else:
                raise RuntimeError(
                    'Unrecognized preview output: {}'.format(msg))
    # exit with code 1 if error happens
    sys.exit(1 if any(msg[1]['name'] == 'stderr'
                      for msg in msgs
                      if msg[0] == 'stream') else 0)


#
# subcommand execute
#


def get_execute_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'execute', description='''Execute a packages task''')
    if desc_only:
        return parser
    parser.add_argument('tasks', nargs='+', help='''IDs of the task.''')
    parser.add_argument(
        '-s',
        choices=['default', 'ignore', 'force', 'build', 'assert', 'skip', 'distributed'],
        default='default',
        metavar='SIGMODE',
        dest='__sig_mode__',
        help='''How runtime signature would be handled, which can be "default"
            (save and use signature, default mode in batch mode), "ignore"
            (ignore runtime signature, default mode in interactive mode),
            "force" (ignore existing signature and overwrite them while
            executing the workflow), "build" (build new or overwrite
            existing signature from existing environment and output files),
            and "assert" for validating existing files against their signatures.
            "skip" and "distributed" are two experimental modes with "skip" for
            bypassing substep as long as step output exists and later than input
            files and "distributed" for sending tasks to subworkers for signature
            validation. Please refer to online documentation for details about
            the use of runtime signatures.''')
    parser.add_argument(
        '-v',
        dest='verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.add_argument(
        '-n',
        '--dryrun',
        action='store_true',
        dest='dryrun',
        help=argparse.SUPPRESS)
    parser.add_argument(
        '-m',
        '--mode',
        dest='run_mode',
        help='''Run mode of the task, default to 'run', but can be 'dryrun' (the
            same as --dryrun) or 'interactive", which suppress status update.''')
    parser.add_argument(
        '-q',
        '--queue',
        help='''Check the status of job on specified tasks queue or remote host
        if the tasks . The queue can be defined in global or local sos
        configuration file, or a file specified by option  --config. A host is
        assumed to be a remote machine with process type if no configuration
        is found.''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-w',
        '--wait',
        action='store_true',
        help='''Wait for the
        completion of the task, and retrieve job results if needed after the
        completion of the task. This option is only valid with the specification
        of the -q option.''')
    parser.set_defaults(func=cmd_execute)
    return parser


def cmd_execute(args, workflow_args):
    from .tasks import check_task, monitor_interval, resource_monitor_interval
    from .task_executor import execute_task
    from .utils import env, load_config_files
    import glob
    if args.queue is None:
        # local machine ...
        exit_code = []
        for task in args.tasks:
            #
            matched = [
                os.path.basename(x)[:-5] for x in glob.glob(
                    os.path.join(
                        os.path.expanduser('~'), '.sos', 'tasks', task +
                        '*.task'))
            ]
            if not matched:
                env.logger.error(
                    '{} does not match any existing task'.format(task))
                exit_code.append(1)
                continue
            elif len(matched) > 1:
                env.logger.error('"{}" matches more than one task ID {}'.format(
                    task, ', '.join(matched)))
                exit_code.append(1)
                continue
            else:
                task = matched[0]
            # this is for local execution, perhaps on a remote host, and
            # there is no daemon process etc. It also does not handle job
            # preparation.
            status = check_task(task)['status']
            if status == 'running':
                print(f'{task} is already running')
                exit_code.append(1)
                continue
            # if status == 'completed' and args.__sig_mode__ != 'force':
            #     # if args.verbosity <= 1:
            #     env.logger.info('{} ``already completed``'.format(task))
            #     with open(os.path.join(os.path.expanduser('~'), '.sos', 'tasks', task + '.err'), 'a') as err:
            #         err.write('{} already completed'.format(task))
            #     # else:
            #     #    print(summarizeExecution(task, status=status))
            #     exit_code.append(0)
            #     continue
            exit_code.append(
                execute_task(
                    task,
                    verbosity=args.verbosity,
                    runmode='dryrun' if args.dryrun else (args.run_mode if args.run_mode else 'run'),
                    sigmode=args.__sig_mode__,
                    monitor_interval=monitor_interval,
                    resource_monitor_interval=resource_monitor_interval))
        sys.exit(sum(exit_code))
    # with queue definition
    from .hosts import Host
    import time
    # this is for local execution using a task queue. The task queue
    # will prepare the task, sync files, and execute this command remotely
    # if needed.
    load_config_files(args.config)
    env.verbosity = args.verbosity
    env.config['sig_mode'] = args.__sig_mode__
    env.config['run_mode'] = 'dryrun' if args.dryrun else (args.run_mode if args.run_mode else 'run')
    host = Host(args.queue)
    for task in args.tasks:
        host.submit_task(task)
    failed_tasks = set()
    while True:
        res = host.check_status(args.tasks)
        if any(x in ('failed', 'aborted') for x in res):
            for t, s in zip(args.tasks, res):
                if s in ('failed', 'aborted') and t not in failed_tasks:
                    env.logger.warning('{} ``{}``'.format(t, s))
                    failed_tasks.add(t)
            if all(x in ('completed', 'failed', 'aborted') for x in res):
                raise RuntimeError(
                    '{} completed, {} failed, {} aborted)'.format(
                        len([x for x in res if x == 'completed']),
                        len([x for x in res if x == 'failed']),
                        len([x for x in res if x.startswith('aborted')])))
        if all(x == 'completed' for x in res):
            if 'TASK' in env.config['SOS_DEBUG'] or 'ALL' in env.config['SOS_DEBUG']:
                env.log_to_file('TASK', f'Put results for {args.tasks}')
            res = host.retrieve_results(args.tasks)
            return
        elif all(x != 'pending' for x in res) and not args.wait:
            return
        elif any(x in ('pending', 'running', 'submitted') for x in res):
            continue
        else:
            raise RuntimeError('Job returned with status {}'.format(res))
        time.sleep(0.01)


#
# command status
#


def get_status_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'status', description='''Check the status of specified tasks''')
    if desc_only:
        return parser
    parser.add_argument(
        'tasks',
        nargs='*',
        help='''ID of the task. All tasks
        that are releted to the workflow executed under the current directory
        will be checked if unspecified. There is no need to specify compelete
        task IDs because SoS will match specified name with tasks starting with
        these names.''')
    parser.add_argument(
        '-q',
        '--queue',
        help='''Check the status of job on specified tasks queue or remote host
        if the tasks . The queue can be defined in global or local sos
        configuration file, or a file specified by option  --config. A host is
        assumed to be a remote machine with process type if no configuration
        is found.''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-a',
        '--all',
        action='store_true',
        help='''Check the status of all tasks on local or specified remote task queue,
        including tasks created by workflows executed from other directories.'''
    )
    parser.add_argument(
        '-v',
        dest='verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2), debug (3) and trace (4)
            information to standard output (default to 2).''')
    parser.add_argument(
        '-t',
        '--tags',
        nargs='*',
        help='''Only list tasks with
        one of the specified tags.''')
    parser.add_argument(
        '-s',
        '--status',
        nargs='*',
        help='''Display tasks with
        one of the specified status.''')
    parser.add_argument(
        '--age',
        help='''Limit to tasks that are created more than
        (default) or within specified age. Value of this parameter can be in units
        s (second), m (minute), h (hour), or d (day, default), or in the foramt of
        HH:MM:SS, with optional prefix + for older (default) and - for newer than
        specified age.''')
    parser.add_argument(
        '--html',
        action='store_true',
        help='''Output results in HTML format. This option will override option
            verbosity and output detailed status information in HTML tables and
            figures.''')
    parser.add_argument(
        '--numeric-times', action='store_true', help=argparse.SUPPRESS)
    parser.set_defaults(func=cmd_status)
    return parser


def cmd_status(args, workflow_args):
    from .tasks import print_task_status
    from .utils import env, load_config_files, get_traceback
    from .hosts import Host
    try:
        load_config_files(args.config)
        if not args.queue:
            print_task_status(
                tasks=args.tasks,
                check_all=args.all,
                verbosity=args.verbosity,
                html=args.html,
                numeric_times=args.numeric_times,
                age=args.age,
                tags=args.tags,
                status=args.status)
        else:
            # remote host?
            host = Host(args.queue, start_engine=False)
            print(
                host._task_engine.query_tasks(
                    tasks=args.tasks,
                    check_all=args.all,
                    verbosity=args.verbosity,
                    html=args.html,
                    numeric_times=args.numeric_times,
                    age=args.age,
                    tags=args.tags,
                    status=args.status))
    except Exception as e:
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


#
# command purge
#


def get_purge_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'purge', description='''Remove local or remote tasks''')
    if desc_only:
        return parser
    parser.add_argument(
        'tasks',
        nargs='*',
        help='''ID of the tasks to be removed.
        There is no need to specify compelete task IDs because SoS will match specified
        name with tasks starting with these names. If no task ID is specified,
        all tasks related to specified workflows (option -w) will be removed.'''
    )
    parser.add_argument(
        '-a',
        '--all',
        action='store_true',
        help='''Clear all task information on local or specified remote task queue,
        including tasks created by other workflows.''')
    parser.add_argument(
        '--age',
        help='''Limit to tasks that are created more than
        (default) or within specified age. Value of this parameter can be in units
        s (second), m (minute), h (hour), or d (day, default), or in the foramt of
        HH:MM:SS, with optional prefix + for older (default) and - for newer than
        specified age.''')
    parser.add_argument(
        '-s',
        '--status',
        nargs='+',
        help='''Only remove tasks with
        specified status, which can be pending, submitted, running, completed, failed,
        and aborted. One of more status can be specified.''')
    parser.add_argument(
        '-t',
        '--tags',
        nargs='*',
        help='''Only remove tasks with
        one of the specified tags.''')
    parser.add_argument(
        '-q',
        '--queue',
        help='''Remove tasks on specified tasks queue or remote host
        if the tasks . The queue can be defined in global or local sos
        configuration file, or a file specified by option  --config. A host is
        assumed to be a remote machine with process type if no configuration
        is found. ''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-v',
        dest='verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2), debug (3) and trace (4)
            information to standard output (default to 2).''')
    parser.set_defaults(func=cmd_purge)
    return parser


def cmd_purge(args, workflow_args):
    from .tasks import purge_tasks
    from .utils import env, load_config_files, get_traceback
    from .hosts import Host
    #from .monitor import summarizeExecution
    env.verbosity = args.verbosity
    try:
        if not args.queue:
            purge_tasks(args.tasks, args.all, args.age, args.status, args.tags,
                        args.verbosity)
        else:
            # remote host?
            load_config_files(args.config)
            host = Host(args.queue)
            print(
                host._task_engine.purge_tasks(args.tasks, args.all, args.age,
                                              args.status, args.tags,
                                              args.verbosity))
    except Exception as e:
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


#
# command kill
#
#
def get_kill_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'kill', description='''Stop the execution of running task''')
    if desc_only:
        return parser
    parser.add_argument(
        'tasks',
        nargs='*',
        help='''IDs of the tasks
        that will be killed. There is no need to specify compelete task IDs because
        SoS will match specified name with tasks starting with these names.''')
    parser.add_argument(
        '-a',
        '--all',
        action='store_true',
        help='''Kill all tasks in local or specified remote task queue''')
    parser.add_argument(
        '-q',
        '--queue',
        help='''Kill jobs on specified tasks queue or remote host
        if the tasks . The queue can be defined in global or local sos
        configuration file, or a file specified by option  --config. A host is
        assumed to be a remote machine with process type if no configuration
        is found.''')
    parser.add_argument(
        '-t',
        '--tags',
        nargs='*',
        help='''Only kill tasks with
        one of the specified tags.''')
    parser.add_argument(
        '-c',
        '--config',
        help='''A configuration file with host
        definitions, in case the definitions are not defined in global sos config.yml files.'''
    )
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_kill)
    return parser


def cmd_kill(args, workflow_args):
    from .tasks import kill_tasks
    from .utils import env, load_config_files
    from .hosts import Host
    env.verbosity = args.verbosity
    if not args.queue:
        if args.all:
            if args.tasks:
                env.logger.warning(
                    'Task ids "{}" are ignored with option --all'.format(
                        ' '.join(args.tasks)))
            if args.tags:
                env.logger.warning('Option tags is ignored with option --all')
            kill_tasks([])
        else:
            if not args.tasks and not args.tags:
                env.logger.warning(
                    'Please specify task id, or one of options --all and --tags'
                )
            else:
                kill_tasks(tasks=args.tasks, tags=args.tags)
    else:
        # remote host?
        load_config_files(args.config)
        host = Host(args.queue)
        print(
            host._task_engine.kill_tasks(
                tasks=args.tasks, tags=args.tags, all_tasks=args.all))


#
# command remove
#


def get_remove_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'remove',
        description='''Remove specified files and/or their signatures''')
    if desc_only:
        return parser
    parser.add_argument(
        'targets',
        nargs='*',
        metavar='FILE_OR_DIR',
        help='''Files and directories to be removed. Directories will be
        scanned for files to removed but no directory will be removed.''')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        '-t',
        '--tracked',
        action='store_true',
        default=False,
        help='''Limit files to only files tracked by SoS, namely files that are
            input, output, or dependent files of steps.''')
    group.add_argument(
        '-u',
        '--untracked',
        action='store_true',
        default=False,
        help='''Limit files to untracked files, namely files that are not
            tracked by SoS steps.''')
    group.add_argument(
        '-s',
        '--signature',
        action='store_true',
        default=False,
        help='''Remove signatures of specified files (not files themselves).
        As a special case, all local signatures will be removed if this option
        is specified without target.''')
    group.add_argument(
        '-z',
        '--zap',
        action='store_true',
        default=False,
        help='''Replace files with their signatures. The file will not be
        regenerated by SoS unless is it actually needed by other steps. This
        option is usually used to remove large intermediate files from
        completed workflows while allowing relevant steps to be skipped
        during re-execution of the workflow.''')
    group.add_argument(
        '-p',
        '--placeholders',
        action='store_true',
        default=False,
        help='''Remove placeholder files that might have been left
        uncleaned after an interrupted dryrun.''')
    parser.add_argument(
        '-e',
        '--external',
        action='store_true',
        default=False,
        help='''By default the remove command will only remove files and
        signatures under the current project directory. This option allows
        sos to remove files and/or signature of external files.''')
    parser.add_argument(
        '--size',
        help='''Limit to files that exceed or smaller than specified size.
        Value of option should be in unit K, M, KB, MB, MiB, GB, etc, with
        optional prefix + for larger than (default), or - for smaller than
        specified size.''')
    parser.add_argument(
        '--age',
        help='''Limit to files that are modified more than
        (default) or within specified age. Value of this parameter can be in units
        s (second), m (minute), h (hour), or d (day, default), or in the foramt of
        HH:MM:SS, with optional prefix + for older (default) and - for newer than
        specified age.''')
    parser.add_argument(
        '-n',
        '--dryrun',
        action='store_true',
        help='''List files or directories to be removed, without actually
            removing them.''')
    parser.add_argument(
        '-y',
        '--yes',
        action='store_true',
        dest='__confirm__',
        help='''Remove files without confirmation, suitable for batch removal
            of files.''')
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_remove)
    return parser


class AnswerMachine:

    def __init__(self, always_yes=False, confirmed=False):
        self._always_yes = always_yes
        self._confirmed = confirmed

    def get(self, msg):
        if self._always_yes:
            return True
        if self._confirmed:
            print(msg)
            return True
        while True:
            res = input('{} (y/n/a)? '.format(msg))
            if res == 'a':
                self._confirmed = True
                return True
            elif res == 'y':
                return True
            elif res == 'n':
                return False


# def get_tracked_files(workflow_id):
#     from .workflow_report import WorkflowSig
#     sig = WorkflowSig(workflow_id)
#     tracked_files = set([x['filename'] for x in sig.tracked_files()])
#     placeholder_files = set(sig.placeholders())
#     return set(), tracked_files, placeholder_files


def cmd_remove(args, unknown_args):
    from .utils import env
    from .targets import file_target
    from .signatures import StepSignatures, WorkflowSignatures

    env.verbosity = args.verbosity

    workflow_signatures = WorkflowSignatures()
    if args.placeholders:
        placeholder_files = workflow_signatures.placeholders()
        removed: int = 0
        for ph in sorted(placeholder_files):
            p = file_target(ph)
            if not p.target_exists('any'):
                continue
            if p.size() == 0:
                try:
                    if 'GENERAL' in env.config['SOS_DEBUG'] or 'ALL' in env.config['SOS_DEBUG']:
                        env.log_to_file('GENERAL',
                                        f'Remove placeholder file {ph}')
                    p.unlink()
                    removed += 1
                except Exception as e:
                    env.logger.debug(
                        f'Failed to remove placeholder file {ph}: {e}')
            else:
                env.logger.debug(
                    f'Keep placeholder {ph} because it is non-empty.')
        if removed:
            env.logger.info(
                f'{removed} placeholder file{"s are" if removed > 1 else "is"} removed'
            )
        else:
            env.logger.info('No remaining placeholder file exists.')
        return

    sig_files = workflow_signatures.files()
    if args.signature:
        # a special case where all file and runtime signatures are removed.
        # no other options are allowed.
        if sig_files:
            sig_ids = list(set([x[0] for x in sig_files]))
            step_signatures = StepSignatures()
            num_removed_steps = step_signatures.remove_many(sig_ids)
            if not num_removed_steps:
                env.logger.info(
                    'No signature is found from workflows executed under the current directory.'
                )
            else:
                env.logger.info(
                    f'Signatures from {num_removed_steps} substeps are removed.'
                )
        else:
            env.logger.info(
                'No signatures is found from workflows executed under the current directory.'
            )
        return
    #
    tracked_files = list(
        set(sum([sum(x[1].values(), []) for x in sig_files], [])))
    if tracked_files:
        env.logger.info(f'{len(tracked_files)} tracked files are identified.')
    else:
        env.logger.info('No tracked file is identified.')
    #
    if not args.targets:
        args.targets = ['.']
    #
    if args.size:
        from .utils import expand_size
        args.size = expand_size(args.size)
    if args.age:
        import time
        from .utils import expand_time
        args.age = expand_time(args.age, default_unit='d')
    if args.tracked:

        def func(filename, resp):
            if os.path.abspath(filename) not in tracked_files:
                env.logger.debug(f'{filename} is not tracked.')
                return False
            target = file_target(filename)
            if target.is_external() and not args.external():
                env.logger.debug('Ignore external file {}'.format(filename))
                return False
            if args.size:
                if (args.size > 0 and os.path.getsize(filename) < args.size) or \
                        (args.size < 0 and os.path.getsize(filename) > -args.size):
                    env.logger.debug('{} ignored due to size limit {}'.format(
                        filename, args.size))
                    return False
            if args.age:
                if (args.age > 0 and time.time() - os.path.getmtime(filename) < args.age) or \
                        (args.age < 0 and time.time() - os.path.getmtime(filename) > -args.age):
                    env.logger.debug('{} ignored due to age limit {}'.format(
                        filename, args.age))
                    return False
            if resp.get('{} tracked file {}'.format(
                    'Would remove' if args.dryrun else 'Remove', filename)):
                if not args.dryrun:
                    env.logger.debug('Remove {}'.format(target))
                    try:
                        target.unlink()
                    except Exception as e:
                        env.logger.warning('Failed to remove {}: {}'.format(
                            filename, e))
                    return True
            else:
                env.logger.debug(
                    'No signature exists for tracked file {}'.format(filename))
            return False
    elif args.untracked:

        def func(filename, resp):
            if os.path.abspath(filename) in tracked_files:
                return False
            target = file_target(filename)
            if target.is_external() and not args.external():
                env.logger.debug('Ignore external file {}'.format(filename))
                return False
            if args.size:
                if (args.size > 0 and os.path.getsize(filename) < args.size) or \
                        (args.size < 0 and os.path.getsize(filename) > -args.size):
                    env.logger.debug('{} ignored due to size limit {}'.format(
                        filename, args.size))
                    return False
            if args.age:
                if (args.age > 0 and time.time() - os.path.getmtime(filename) < args.age) or \
                        (args.age < 0 and time.time() - os.path.getmtime(filename) > -args.age):
                    env.logger.debug('{} ignored due to age limit {}'.format(
                        filename, args.age))
                    return False
            if resp.get('{} untracked file {}'.format(
                    'Would remove' if args.dryrun else 'Remove', filename)):
                if not args.dryrun:
                    env.logger.debug('Remove {}'.format(target))
                    try:
                        target.unlink()
                    except Exception as e:
                        env.logger.warning('Failed to remove {}: {}'.format(
                            filename, e))
                    return True
            else:
                env.logger.debug(
                    'No signature exists for tracked file {}'.format(filename))
            return False
    elif args.zap:

        def func(filename, resp):
            target = file_target(filename)
            if target.is_external() and not args.external():
                env.logger.debug('Ignore external file {}'.format(filename))
                return False
            if args.size:
                if (args.size > 0 and os.path.getsize(filename) < args.size) or \
                        (args.size < 0 and os.path.getsize(filename) > -args.size):
                    env.logger.debug('{} ignored due to size limit {}'.format(
                        filename, args.size))
                    return False
            if args.age:
                if (args.age > 0 and time.time() - os.path.getmtime(filename) < args.age) or \
                        (args.age < 0 and time.time() - os.path.getmtime(filename) > -args.age):
                    env.logger.debug('{} ignored due to age limit {}'.format(
                        filename, args.age))
                    return False
            if resp.get('{} tracked file {}'.format(
                    'Would zap' if args.dryrun else 'Zap', filename)):
                if not args.dryrun:
                    env.logger.debug('Zap {}'.format(target))
                    try:
                        file_target(target).zap()
                    except Exception as e:
                        env.logger.warning('Failed to zap {}: {}'.format(
                            filename, e))
                    return True
            else:
                env.logger.debug(
                    'No signature exists for tracked file {}'.format(filename))
            return False
    else:
        # default behavior
        def func(filename, resp):
            target = file_target(filename)
            if target.is_external() and not args.external():
                env.logger.debug('Ignore external file {}'.format(filename))
                return False
            if args.size:
                if (args.size > 0 and os.path.getsize(filename) < args.size) or \
                        (args.size < 0 and os.path.getsize(filename) > -args.size):
                    env.logger.debug('{} ignored due to size limit {}'.format(
                        filename, args.size))
                    return False
            if args.age:
                if (args.age > 0 and time.time() - os.path.getmtime(filename) < args.age) or \
                        (args.age < 0 and time.time() - os.path.getmtime(filename) > -args.age):
                    env.logger.debug('{} ignored due to age limit {}'.format(
                        filename, args.age))
                    return False
            if resp.get('{} file {}'.format(
                    'Would remove' if args.dryrun else 'Remove', filename)):
                if not args.dryrun:
                    env.logger.debug('Remove {}'.format(target))
                    try:
                        target.unlink()
                    except Exception as e:
                        env.logger.warning('Failed to remove {}: {}'.format(
                            filename, e))
                    return True
            else:
                env.logger.debug(
                    'No signature exists for tracked file {}'.format(filename))
            return False

    removed = 0
    resp = AnswerMachine(always_yes=args.dryrun, confirmed=args.__confirm__)
    for target in args.targets:
        target = os.path.expanduser(target)
        if file_target(target).is_external():
            if os.path.isdir(target):
                sys.exit('Canot remove external directory {}'.format(target))
            elif not args.external:
                sys.exit(
                    'Only subdirectories of the current directory can be removed unless option --external is specified. {} specified.'
                    .format(target))
        if os.path.isfile(target):
            removed += func(target, resp)
            continue
        # directory
        for dirname, dirlist, filelist in os.walk(target):
            # we do not remove files under the current directory
            if dirname != '.':
                for x in filelist:
                    # ignore hidden file
                    if x.startswith('.'):
                        continue
                    removed += func(os.path.join(dirname, x), resp)
            dirlist[:] = [x for x in dirlist if not x.startswith('.')]
    env.logger.info('{}{} file{} {}'.format(
        'Signagure of ' if args.signature else '', removed,
        's' if removed > 1 else '', 'zapped' if args.zap else 'removed'))


#
# subcommand config
#


def get_config_parser(desc_only=False):
    parser = argparse.ArgumentParser(
        'config',
        description='''Displays configurations in host, global, local, and user specified
            configuration files. ''')
    parser.short_description = '''Read and write sos configuration files'''
    if desc_only:
        return parser
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '-s',
        '--site',
        action='store_true',
        dest='__site_config__',
        help='''Set (--set) or unset (--unset) options in system site configuration file
            (${SOS}/site_config.yml).''')
    group.add_argument(
        '-g',
        '--global',
        action='store_true',
        dest='__global_config__',
        help=argparse.SUPPRESS)
    group.add_argument(
        '--hosts',
        action='store_true',
        dest='__hosts_config__',
        help='''Set (--set) or unset (--unset) options in hosts (~/.sos/hosts.yml)'''
    )
    group.add_argument(
        '-c',
        '--config',
        dest='__config_file__',
        metavar='CONFIG_FILE',
        help='''Set (--set) or unset (--unset) options in user specified configuration file,
            or display options (--get) also in this file.''')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        '--get',
        nargs='*',
        metavar='OPTION',
        dest='__get_config__',
        help='''Display values of options that contain one of the specified words
            from all configuration files.''')
    group.add_argument(
        '--unset',
        nargs='+',
        metavar='OPTION',
        dest='__unset_config__',
        help='''Unset (remove) settings for specified options. The arguments of this
        option can be a single configuration option or a list of option. Wildcard
        characters are allowed to match more options (e.g. '*timeout', or '*' for
        all options, quotation is needed to avoid shell expansion).''')
    group.add_argument(
        '--set',
        nargs='+',
        metavar='KEY VALUE',
        dest='__set_config__',
        help='''--set KEY VALUE sets VALUE to variable KEY. The value can be any valid
        python expression (e.g. 5 for integer 5 and '{"c": 2, "d": 1}' for a dictionary)
        with invalid expression (e.g. val without quote) considered as string. Syntax
        'A.B=v' can be used to add {'B': v} to dictionary 'A', and --set KEY VALUE1 VALUE2 ...
        will create a list with multiple values.''')
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=range(5),
        default=2,
        help='''Output error (0), warning (1), info (2) and debug (3)
            information to standard output (default to 2). More debug information could be
            generated by setting environmental variable SOS_DEBUG to comma separated topics
            of GENERAL, WORKER, CONTROLLER, STEP, VARIABLE, EXECUTOR, TARGET, ZERONQ, TASK,
            DAG, and ACTION, or ALL for all debug information''')
    parser.set_defaults(func=cmd_config)
    return parser


def cmd_config(args, workflow_args):
    import fnmatch
    import yaml
    from .utils import env, dict_merge, load_config_files
    from .syntax import CONFIG_NAME
    if workflow_args:
        raise RuntimeError('Unrecognized arguments {}'.format(
            ' '.join(workflow_args)))
    #
    if args.__unset_config__:
        if args.__site_config__:
            config_file = os.path.join(
                os.path.split(__file__)[0], 'site_config.yml')
        elif args.__hosts_config__:
            config_file = os.path.join(
                os.path.expanduser('~'), '.sos', 'hosts.yml')
        elif args.__config_file__:
            config_file = os.path.expanduser(args.__config_file__)
        else:
            config_file = os.path.join(
                os.path.expanduser('~'), '.sos', 'config.yml')

        if os.path.isfile(config_file):
            try:
                with open(config_file) as config:
                    cfg = yaml.safe_load(config)
                if cfg is None:
                    cfg = {}
            except Exception as e:
                env.logger.error(
                    'Failed to parse sos config file {}, is it in YAML/JSON format? ({})'
                    .format(config_file, e))
                sys.exit(1)
        else:
            env.logger.error(
                'Config file {} does not exist'.format(config_file))
            sys.exit(1)
        #

        def unset_key(prefix, cfg):
            changed = 0
            unset = []
            for option in args.__unset_config__:
                for k in cfg.keys():
                    if fnmatch.fnmatch('.'.join(prefix + [k]), option):
                        unset.append(k)
                        print('Unset {}'.format('.'.join(prefix + [k])))
            #
            if unset:
                changed += len(unset)
                for k in set(unset):
                    cfg.pop(k)

            for k, v in cfg.items():
                if isinstance(v, dict):
                    changed += unset_key(prefix + [k], v)
            return changed

        #
        if unset_key([], cfg):
            with open(config_file, 'w') as config:
                config.write(yaml.safe_dump(cfg, default_flow_style=False))
        else:
            env.logger.warning('{} does not match any configuration key'.format(
                ', '.join(args.__unset_config__)))
    elif args.__set_config__:
        if args.__site_config__:
            config_file = os.path.join(
                os.path.split(__file__)[0], 'site_config.yml')
        elif args.__hosts_config__:
            config_file = os.path.join(
                os.path.expanduser('~'), '.sos', 'hosts.yml')
        elif args.__config_file__:
            config_file = os.path.expanduser(args.__config_file__)
        else:
            config_file = os.path.join(
                os.path.expanduser('~'), '.sos', 'config.yml')

        if os.path.isfile(config_file):
            try:
                with open(config_file) as config:
                    cfg = yaml.safe_load(config)
                if cfg is None:
                    cfg = {}
            except Exception as e:
                env.logger.error(
                    'Failed to sos config file {}, is it in YAML/JSON format? ({})'
                    .format(config_file, e))
                sys.exit(1)
        else:
            cfg = {}
        #
        if len(args.__set_config__) == 1:
            env.logger.error('Please specify a value for key {}'.format(
                args.__set_config__[0]))
            sys.exit(1)
        #
        k = args.__set_config__[0]
        if not CONFIG_NAME.match(k):
            env.logger.error('Unacceptable variable name {}.'.format(k))
            sys.exit(1)
        #
        values = []
        for v in args.__set_config__[1:]:
            try:
                v_val = ast.literal_eval(v)
                # test if the value can be saved by yaml
                yaml.safe_dump(v_val)
                v = v_val
            except Exception:
                env.logger.debug(
                    'Value "{}" is an invalid expression and is treated as a string.'
                    .format(v))
            values.append(v)
        #
        if len(values) == 1:
            values = values[0]
        #
        # say v   = 1
        #     key = a.b.c
        #
        # this gives:
        #     {'a': {'b': {'c': 1}}}
        dv = values
        for key in reversed(k.split('.')):
            new_dv = {}
            new_dv[key] = dv
            dv = new_dv
        # however we can not update directly and has to merge two
        # dictionaries. For example, if
        #
        # cfg = {'a': {'b': {'d': 2}}, {'c': 1}}
        #
        # we need to get
        #
        # cfg = {'a': {'b': {'d': 2, 'c': 1}}, {'c': 1}}
        #
        dict_merge(cfg, dv)
        # reporting assignment with existing values
        print('Set {} to {!r}'.format(k.split('.')[0], cfg[k.split('.')[0]]))
        #
        with open(config_file, 'w') as config:
            config.write(yaml.safe_dump(cfg, default_flow_style=False))
    elif args.__get_config__ is not None:
        cfg = load_config_files(args.__config_file__)

        def disp_matched(obj, options, prefix=[]):
            for k, v in obj.items():
                key = '.'.join(prefix + [k])
                if isinstance(v, dict):
                    disp_matched(v, options, prefix + [k])
                elif not options or any(option in key for option in options):
                    print('{}\t{!r}'.format(key, v))

        disp_matched(cfg, args.__get_config__)
    else:
        from pprint import PrettyPrinter
        pp = PrettyPrinter(indent=2)
        cfg = load_config_files(args.__config_file__)
        pp.pprint(cfg)


#
# Handling addon commands
#
def handle_addon(args, unknown_args):
    for entrypoint in pkg_resources.iter_entry_points(group='sos_addons'):
        name = entrypoint.name.strip()
        if name.endswith('.func') and name.rsplit('.', 1)[0] == args.addon_name:
            func = entrypoint.load()
            func(args, unknown_args)


#
# this is the sos-runner command
#


def sosrunner():
    parser = get_run_parser()
    parser.prog = 'sos-runner'
    if len(sys.argv) > 2 and '-h' in sys.argv:
        try:
            from .parser import SoS_Script
            script = SoS_Script(filename=sys.argv[1])
            script.print_help(sys.argv[1])
            sys.exit(0)
        except Exception as e:
            sys.exit(
                'No help information is available for script {}: {}'.format(
                    sys.argv[1], e))
    args, workflow_args = parser.parse_known_args()
    cmd_run(args, workflow_args)


# add another ArgumentParser to an existing ArgumentParser as
# a subparser
#
def add_sub_parser(subparsers, parser, name=None, hidden=False):
    if hidden:
        return subparsers.add_parser(
            parser.prog if name is None else name,
            description=parser.description,
            epilog=parser.epilog,
            parents=[parser],
            add_help=False)
    else:
        return subparsers.add_parser(
            parser.prog if name is None else name,
            description=parser.description,
            epilog=parser.epilog,
            help=parser.short_description
            if hasattr(parser, 'short_description') else parser.description,
            parents=[parser],
            add_help=False)


def main():
    from ._version import SOS_FULL_VERSION

    # only load specific subparser to save on start-up time
    if len(sys.argv) == 1 or sys.argv[1] == '-h':
        subcommand = None
    else:
        subcommand = sys.argv[1]

    master_parser = argparse.ArgumentParser(
        description='''A workflow system
            for the execution of commands and scripts in different languages.''',
        prog='sos',
        fromfile_prefix_chars='@',
        epilog='''Use 'sos cmd -h' for details about each subcommand. Please
            contact Bo Peng (bpeng at mdanderson.org) if you have any question.'''
    )

    try:
        master_parser.add_argument(
            '--version',
            action='version',
            version='%(prog)s {}'.format(SOS_FULL_VERSION))
        subparsers = master_parser.add_subparsers(
            title='subcommands',
            metavar='{install,run,dryrun,status,push,pull,execute,kill,purge,config,convert,remove}'
        )

        # command install
        # add_sub_parser(subparsers, get_install_parser(desc_only='install'!=subcommand))
        #
        # command run
        add_sub_parser(subparsers,
                       get_run_parser(desc_only='run' != subcommand))
        #
        # command dryrun
        add_sub_parser(subparsers,
                       get_dryrun_parser(desc_only='dryrun' != subcommand))

        #
        # command status
        add_sub_parser(subparsers,
                       get_status_parser(desc_only='status' != subcommand))
        #
        # command push, replaced by sos remote push
        add_sub_parser(
            subparsers,
            get_push_parser(desc_only='push' != subcommand),
            hidden=True)
        #
        # command pull, replaced by sos remote pull
        add_sub_parser(
            subparsers,
            get_pull_parser(desc_only='pull' != subcommand),
            hidden=True)
        #
        # command remote
        add_sub_parser(subparsers,
                       get_remote_parser(desc_only='remote' != subcommand))
        #
        # command preview
        add_sub_parser(
            subparsers,
            get_preview_parser(desc_only='preview' != subcommand),
            hidden=True)
        #
        # command execute
        add_sub_parser(subparsers,
                       get_execute_parser(desc_only='execute' != subcommand))
        #
        # command kill
        add_sub_parser(subparsers,
                       get_kill_parser(desc_only='kill' != subcommand))
        #
        # command purge
        add_sub_parser(subparsers,
                       get_purge_parser(desc_only='purge' != subcommand))

        #
        # command config
        add_sub_parser(subparsers,
                       get_config_parser(desc_only='config' != subcommand))
        #
        # command convert
        add_sub_parser(subparsers,
                       get_convert_parser(desc_only='convert' != subcommand))
        #
        # command remove
        add_sub_parser(subparsers,
                       get_remove_parser(desc_only='remove' != subcommand))
        #
        # addon packages
        if subcommand is None or subcommand not in [
                'install', 'run', 'dryrun', 'convert', 'push', 'pull', 'remove',
                'config'
        ]:
            for entrypoint in pkg_resources.iter_entry_points(
                    group='sos_addons'):
                if entrypoint.name.strip().endswith('.parser'):
                    name = entrypoint.name.rsplit('.', 1)[0]
                    func = entrypoint.load()
                    parser = add_sub_parser(subparsers, func(), name=name)
                    parser.add_argument(
                        '--addon-name', help=argparse.SUPPRESS, default=name)
                    parser.set_defaults(func=handle_addon)
        #
        if len(sys.argv) == 1 or sys.argv[1] == '-h':
            master_parser.print_help()
            sys.exit(0)
        if '-h' in sys.argv:
            if len(sys.argv) > 3 and sys.argv[
                    1] == 'run' and not sys.argv[2].startswith('-'):
                try:
                    from .parser import SoS_Script
                    script = SoS_Script(filename=sys.argv[2])
                    script.print_help(sys.argv[2])
                    sys.exit(0)
                except Exception as e:
                    sys.exit(
                        'No help information is available for script {}: {}'
                        .format(sys.argv[1], e))
            if len(sys.argv) > 3 and sys.argv[1] == 'convert':
                print_converter_help()
        elif sys.argv[1] == 'convert':
            # this command has to be processed separately because I hat to use
            # sos convert sos-html FROM TO etc
            from_format, to_format = get_converter_formats(sys.argv[2:])
            if from_format is None or to_format is None:
                sys.exit('Cannot determine from or to format')
            sys.argv.insert(2, '{}-{}'.format(from_format, to_format))
        args, workflow_args = master_parser.parse_known_args()
        if not hasattr(args, 'func'):
            # in case of sos -v etc that no subcommand is specified
            master_parser.print_help()
            sys.exit(0)
        # calling the associated functions
        args.func(args, workflow_args)
    except KeyboardInterrupt:
        sys.exit('KeyboardInterrupt')
    except Exception as e:
        from .utils import env, get_traceback
        if env.verbosity and env.verbosity > 2:
            sys.stderr.write(get_traceback())
        env.logger.error(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
