#!/usr/bin/env python3
import argparse
import glob
import logging
import os
import shutil
import stat
import sys
import traceback
from typing import Any, Dict, List, Mapping

import jinja2
import yaml


DIR_PATH = os.path.dirname(os.path.realpath(__file__))
TEST_CASE_DIR = os.path.join(DIR_PATH, 'test_cases')
FILES_DIR = os.path.join(DIR_PATH, 'files')


def prepare_dir(directory: str, clean: bool = False) -> None:
    if clean:
        try:
            shutil.rmtree(directory)
        except FileNotFoundError:
            pass
    try:
        os.makedirs(directory)
    except FileExistsError as e:
        raise RuntimeError(
            'Directory "{}" already exists! Use -l label / --clean or (re)move the '
            'directory manually to resolve the issue.'.format(directory)) from e


def copy_file(name: str, destdir: str, destname: str = ''):
    if not destname:
        destname = name
    shutil.copy(
        os.path.join(FILES_DIR, name),
        os.path.join(destdir, destname))


def create_file_from_template(
            name: str,
            data: Mapping[str, Any],
            destdir: str,
            destname: str = '',
            executable=False
        ) -> None:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(FILES_DIR))
    template = env.get_template(name)
    rendered = template.render(**data)

    if not destname:
        assert name[-3:] == '.j2'
        destname = os.path.basename(name)[:-3]
    dest = os.path.join(destdir, destname)
    with open(dest, 'w') as fh:
        fh.write(rendered)

    if executable:
        st = os.stat(dest)
        os.chmod(dest, st.st_mode | stat.S_IEXEC)


def load_test_case_config(test_case: str) -> Dict[str, Any]:
    path = os.path.join(TEST_CASE_DIR, test_case + '.yaml')
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def create_resolver_configs(directory: str, config: Dict[str, Any]):
    for name, resolver in config['resolvers'].items():
        resolver['name'] = name
        resolver['verbose'] = config['verbose']
        if resolver['type'] == 'knot-resolver':
            dockerfile_dir = os.path.join(directory, 'docker-knot-resolver')
            if not os.path.exists(dockerfile_dir):
                os.makedirs(dockerfile_dir)
                copy_file('Dockerfile.knot-resolver', dockerfile_dir, 'Dockerfile')
                copy_file('kresd.entrypoint.sh', dockerfile_dir)
            create_file_from_template(
                'kresd.conf.j2', resolver, directory, name + '.conf')
        elif resolver['type'] == 'unbound':
            create_file_from_template(
                'unbound.conf.j2', resolver, directory, name + '.conf')
            copy_file('cert.pem', directory)
            copy_file('key.pem', directory)
            copy_file('root.keys', directory)
        elif resolver['type'] == 'bind':
            create_file_from_template(
                'named.conf.j2', resolver, directory, name + '.conf')
            copy_file('rfc1912.zones', directory)
            copy_file('bind.keys', directory)
        else:
            raise NotImplementedError(
                "unknown resolver type: '{}'".format(resolver['type']))


def create_resperf_files(directory: str, config: Dict[str, Any]):
    create_file_from_template('run_resperf.sh.j2', config, directory, executable=True)
    create_file_from_template('docker-compose.yaml.j2', config, directory)
    create_resolver_configs(directory, config)


def create_distrotest_files(directory: str, config: Dict[str, Any]):
    create_file_from_template('run_distrotest.sh.j2', config, directory, executable=True)


def create_respdiff_files(directory: str, config: Dict[str, Any]):
    create_file_from_template('run_respdiff.sh.j2', config, directory, executable=True)
    create_file_from_template('restart-all.sh.j2', config, directory, executable=True)
    create_file_from_template('docker-compose.yaml.j2', config, directory)
    create_resolver_configs(directory, config)

    # omit resolvers without respdiff section from respdiff.cfg
    config['resolvers'] = {
        name: res for name, res
        in config['resolvers'].items()
        if 'respdiff' in res}
    create_file_from_template('respdiff.cfg.j2', config, directory)

    if config['respdiff_stats']:  # copy optional stats file
        try:
            shutil.copyfile(config['respdiff_stats'], os.path.join(directory, 'stats.json'))
        except FileNotFoundError as e:
            raise RuntimeError(
                "Statistics file not found: {}".format(config['respdiff_stats'])) from e


def create_template_files(directory: str, config: Dict[str, Any]):
    if 'respdiff' in config:
        create_respdiff_files(directory, config)
    elif 'resperf' in config:
        create_resperf_files(directory, config)
    elif 'distrotest' in config:
        create_distrotest_files(directory, config)


def get_test_case_list(nameglob: str = '') -> List[str]:
    # test cases end with '*.jXXX' implying a number of jobs (less -> longer runtime)
    # return them in ascending order, so more time consuming test cases run first
    return sorted([
        os.path.splitext(os.path.basename(fname))[0]
        for fname in glob.glob(os.path.join(TEST_CASE_DIR, '{}*.yaml'.format(nameglob)))],
        key=lambda x: x.split('.')[-1])  # sort by job count


def create_jobs(args: argparse.Namespace) -> None:
    test_cases = []  # type: List[str]
    if args.t is not None:
        test_cases.append(args.t)
    else:
        test_cases = get_test_case_list(args.all)
    if not test_cases:
        raise RuntimeError("No test cases found!")

    git_sha = args.sha_or_tag
    commit_dir = git_sha
    if args.label is not None:
        if ' ' in args.label:
            raise RuntimeError('Label may not contain spaces.')
        commit_dir += '-' + args.label

    for test_case in test_cases:
        config = load_test_case_config(test_case)
        config['git_sha'] = git_sha
        config['knot_branch'] = args.knot_branch
        config['verbose'] = args.verbose
        config['asan'] = args.asan
        config['log_keys'] = args.log_keys
        config['respdiff_stats'] = args.respdiff_stats
        config['obs_repo'] = args.obs_repo
        config['package'] = args.package

        directory = os.path.join(args.jobs_dir, commit_dir, test_case)
        prepare_dir(directory, clean=args.clean)
        create_template_files(directory, config)

        # print out created directory so it can be supplied as argument(s)
        # for submit.py
        print(directory)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare files for docker respdiff job")
    parser.add_argument(
        'sha_or_tag', type=str,
        help="Knot Resolver git commit or tag to use (don't use branch!)")
    parser.add_argument(
        '-a', '--all', default='shortlist',
        help="Create all test cases which start with expression (default: shortlist)")
    parser.add_argument(
        '-t', choices=get_test_case_list(),
        help="Create only the specified test case")
    parser.add_argument(
        '-l', '--label',
        help="Assign label for easier job identification and isolation")
    parser.add_argument(
        '--clean', action='store_true',
        help="Remove target directory if it already exists (use with caution!)")
    parser.add_argument(
        '--jobs-dir', default='/var/tmp/respdiff-jobs',
        help="Directory with job collections (default: /var/tmp/respdiff-jobs)")
    parser.add_argument(
        '--knot-branch', type=str, default='3.0',
        help="Build knot-resolver against selected Knot DNS branch")
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help="Capture verbose logs (kresd, unbound)")
    parser.add_argument(
        '--asan', action='store_true',
        help="Build with Address Sanitizer")
    parser.add_argument(
        '--log-keys', action='store_true',
        help="Log TLS session keys (kresd)")
    parser.add_argument(
        '--respdiff-stats', type=str, default='',
        help=("Statistics file to generate extra respdiff report(s) with omitted "
              "unstable/failing queries"))
    parser.add_argument(
        '--obs-repo', type=str, default='knot-resolver-devel',
        help=("OBS repository for distrotests (default: knot-resolver-devel)"))
    parser.add_argument(
        '--package', type=str, default='knot-resolver',
        help=("package for distrotests (default: knot-resolver)"))

    args = parser.parse_args()
    create_jobs(args)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(levelname)8s  %(message)s', level=logging.DEBUG)
    try:
        main()
    except RuntimeError as exc:
        logging.debug(traceback.format_exc())
        logging.error(str(exc))
        sys.exit(1)
    except Exception as exc:
        logging.debug(traceback.format_exc())
        logging.critical('Unhandled code exception: %s', str(exc))
        sys.exit(2)
