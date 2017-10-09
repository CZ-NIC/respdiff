'''
Created on May 25, 2017

@author: Jan Holusa
'''

from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
import logging
import os
import sys
import socket
import telnetlib

log = logging.getLogger()


class Params(object):
    '''
    Parameters holder
    '''

    def __init__(self):
        '''
        Constructor
        '''
        self.ip = ''
        self.port = ''
        self.config = ''
        self.user = ''
        self.kill_flag = False
        self.path, tail = os.path.split(os.path.dirname(os.path.abspath(__file__)))
        self.script_folder = os.path.join(self.path, "script")
        self.resolver = ""
        self.local_port = ""

    def read_params(self, argv=None):  # IGNORE:C0111
        '''Command line options.'''
        possible_resolvers = ['knot', 'bind', 'unbound', 'pdns']
        if argv is None:
            argv = sys.argv
        else:
            sys.argv.extend(argv)

        program_name = os.path.basename(sys.argv[0])
        program_version = "v0.1"
        program_build_date = "31.5.2017"
        program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
        program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
        program_license = '''%s

      Created by Jan Holusa on %s.
      Copyright 2017 nic.cz. All rights reserved.
''' % (program_shortdesc, "31.5.2017")

        try:
            # Setup argument parse_result
            parse_result = ArgumentParser(
                description=program_license,
                formatter_class=RawDescriptionHelpFormatter)
            parse_result.add_argument(
                "-i", "--ip", dest="ip", help="Set ip to run resolver", required=True)
            parse_result.add_argument(
                "-p", "--port", dest="port", help="Set port to run resolver", required=True)
            parse_result.add_argument(
                "-u", "--user", dest="user",
                help="User defined on remote server with granted acess", required=True)
            parse_result.add_argument(
                '-k', '--kill', dest='kill', help="Kill running remote server.",
                action='store_true', default=False)
            parse_result.add_argument(
                '-r', '--resolver', dest='resolver',
                help="Which resolver I should start. Possible values are: %s" % ", ".join(
                    map(str, possible_resolvers)))
            parse_result.add_argument(
                '-l', '--local_port', dest='local_port',
                help="Name of the local port. For example eth0, tun4 and so on...")
            parse_result.add_argument(
                '-V', '--version', action='version', version=program_version_message)

            # Process arguments
            args = parse_result.parse_args()
            self.kill_flag = args.kill

            if not(self.kill_flag):

                if args.local_port:
                    self.local_port = args.local_port
                    log.debug("Local port name: %s" % self.local_port)
                else:
                    log.error("Missing local port name.")
                    raise IOError(
                        "Missing local port name. For example: eth0, tun4... " +
                        "use ifconfig (or ipconfig)")

                if args.resolver:
                    if args.resolver in possible_resolvers:
                        self.resolver = args.resolver
                        log.debug("resolver: %s" % self.resolver)
                        self.config = os.path.join(self.path, "config")
                    else:
                        log.error("Not supported resolver. Possible values are: %s" %
                                  ", ".join(map(str, possible_resolvers)))
                        raise IOError("Not supported resolver. Possible values are: %s" %
                                      ", ".join(map(str, possible_resolvers)))
                else:
                    log.error("Missing resolver argument.")
                    raise IOError("Missing resolver argument.")
#                 else:
#                     log.error("Missing config file.")
#                     raise IOError("Missing config file.")

            if args.user:
                self.user = args.user
                log.debug("User: %s" % self.user)
            else:
                log.error("Missing user name file.")
                raise IOError("Missing user name file.")
            if args.ip:
                self.ip = args.ip
                log.debug("Ip: %s" % self.ip)
            else:
                log.error("Missing ip address of remote server.")
                raise IOError("Missing ip address of remote server.")
            if args.port:
                self.port = args.port
                log.debug("port: %s" % self.port)
            else:
                log.error("Missing port of remote server.")
                raise IOError("Missing port of remote server.")

            if not(self.kill_flag):
                try:
                    tn = telnetlib.Telnet(self.ip, self.port)
                except BaseException:
                    log.debug("Given port is free - OK.")
                else:
                    log.error("Given port is occupied by some service. Try another port.")
                    raise IOError("Given port is occupied by some service. Try another port.")

        except KeyboardInterrupt:
            # handle keyboard interrupt
            return 0
        except Exception as e:
            indent = len(program_name) * " "
            sys.stderr.write(program_name + ": " + repr(e) + "\n")
            sys.stderr.write(indent + "  for help use --help\n")
            raise e

    def check_server(self, ip, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((ip, int(port)))

        if result == 0:
            log.info('Address: %s:%s is open.' % (ip, port))
            print(
                "Seems that server just started :] Port is open. Don't forget to kill it after use."
            )
        else:
            log.info('Address: %s:%s is NOT open.' % (ip, port))
            print("Seems that server just stopped :] Port is closed.")

# class Params end
