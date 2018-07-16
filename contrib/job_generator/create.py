#!/usr/bin/env python3
import argparse
import glob
import os
import shutil
import subprocess

import jinja2
import yaml


DIR_PATH = os.path.dirname(os.path.realpath(__file__))
CONFIG_DIR = os.path.join(DIR_PATH, 'configs')
FILES_DIR = os.path.join(DIR_PATH, 'files')


def ensure_dir_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


def copy_file(name, destdir):
    ensure_dir_exists(os.path.dirname(destdir))
    shutil.copy(
        os.path.join(FILES_DIR, name),
        os.path.join(destdir, os.path.basename(name)))
    return os.path.basename(name)


def create_file_from_template(template_filename, destdir, data, name=None, chmod=None):
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(FILES_DIR))
    template = env.get_template(template_filename)
    rendered_template = template.render(**data)

    ensure_dir_exists(destdir)
    if name is None:
        name = os.path.basename(template_filename)[:-3]
    dest = os.path.join(destdir, name)
    with open(dest, 'w') as fh:
        fh.write(rendered_template)

    if chmod is not None:
        os.chmod(dest, chmod)

    return name


def load_job_config(name):
    path = os.path.join(CONFIG_DIR, name + '.yaml')
    with open(path, 'r') as f:
        return yaml.load(f)


def create_job(job_config):
    jobdir = os.path.join(
        job_config['jobdir'], job_config['git_sha'], job_config['name'])
    input_files = []
    ensure_dir_exists(jobdir)
    input_files.append(create_file_from_template(
        'run_respdiff.sh.j2', jobdir, job_config, chmod=0o755))
    input_files.append(create_file_from_template(
        'restart-all.sh.j2', jobdir, job_config, chmod=0o755))
    input_files.append(create_file_from_template(
        'docker-compose.yaml.j2', jobdir, job_config))

    for name, resolver in job_config['resolvers'].items():
        resolver['name'] = name
        if resolver['type'] == 'knot-resolver':
            input_files.append('docker-knot-resolver/Dockerfile')
            dockerfile_dir = os.path.join(jobdir, 'docker-knot-resolver')
            if not os.path.exists(dockerfile_dir):
                os.makedirs(dockerfile_dir)
                copy_file('docker-knot-resolver/Dockerfile', dockerfile_dir)
            input_files.append(create_file_from_template(
                'kresd.conf.j2', jobdir, resolver, name + '.conf'))
            input_files.append(copy_file('root.keys', jobdir))
        elif resolver['type'] == 'unbound':
            input_files.append(create_file_from_template(
                'unbound.conf.j2', jobdir, resolver, name + '.conf'))
            input_files.append(copy_file('cert.pem', jobdir))
            input_files.append(copy_file('key.pem', jobdir))
            input_files.append(copy_file('root.keys', jobdir))
        elif resolver['type'] == 'bind':
            input_files.append(create_file_from_template(
                'named.conf.j2', jobdir, resolver, name + '.conf'))
            input_files.append(copy_file('rfc1912.zones', jobdir))
            input_files.append(copy_file('bind.keys', jobdir))
        else:
            raise NotImplementedError(
                "unknown resolver type: '{}'".format(resolver['type']))

    # omit resolvers without respdiff section from respdiff.cfg
    job_config['resolvers'] = {
        name: res for name, res in job_config['resolvers'].items() if 'respdiff' in res}
    input_files.append(create_file_from_template(
        'respdiff.cfg.j2', jobdir, job_config))

    # create condor job file
    create_file_from_template('submit.condor.j2', jobdir, {
        'input_files': set(input_files),
        'batch_name': "{}-{}".format(job_config['git_sha'][:7], job_config['name'])})

    return jobdir


def get_job_list(db_name=''):
    return [
        os.path.splitext(os.path.basename(fname))[0]
        for fname in glob.glob(os.path.join(CONFIG_DIR, '{}*.yaml'.format(db_name)))]


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a Knot Resolver CI testing job for respdiff")
    parser.add_argument(
        'sha_or_tag', type=str,
        help="Knot Resolver git commit or tag to use (don't use branch!)")
    parser.add_argument(
        '-a', '--all', default='shortlist',
        help="Create all jobs for specified db (default: shortlist)")
    parser.add_argument(
        '-j', '--job', choices=get_job_list(),
        help="Specific job configuration file")
    parser.add_argument(
        '-q', '--queue', type=int,
        help="Submit as a condor job")
    parser.add_argument(
        '-p', '--priority', type=int,
        help="Set condor job priority (higher = sooner exec)")
    args = parser.parse_args()

    jobs = []
    if args.job is not None:
        jobs.append(args.job)
    else:
        jobs = get_job_list(args.all)
    if not jobs:
        raise RuntimeError("No job configs found!")

    for job in jobs:
        job_config = load_job_config(job)
        job_config['name'] = os.path.basename(job)
        job_config['git_sha'] = args.sha_or_tag
        if args.queue is not None:
            job_config['condor']['queue'] = args.queue
        if args.priority is not None:
            job_config['condor']['priority'] = args.priority
        jobdir = create_job(job_config)
        if job_config['condor']['queue']:
            subprocess.check_call([
                'condor_submit',
                'priority={}'.format(job_config['condor']['priority']),
                'submit.condor',
                '-queue', str(job_config['condor']['queue'])],
                cwd=jobdir)


if __name__ == '__main__':
    main()
