'''
Created on May 25, 2017

@author: Jan Holusa
'''
import os
import subprocess
import logging
from xmlrpclib import INTERNAL_ERROR
import socket
import fcntl
import struct
from _threading_local import local

log = logging.getLogger() 

class MaintainResolver(object):
    def __init__(self, params):
        self.params = params
        self.tmp = os.path.join('/tmp/',self.params.user+'/')            
        
    def prepare_resolvers(self):
        '''
        Uploads script and config files to foreign servers depending
        on configuration of IP's of servers.
        Folders are stored in /tmp/. And run that server
        '''                                    
        local_ip = self.get_ip_address(self.params.local_port)
#         print "local_ip:"+local_ip
        ## Send config folder
        log.info("Copying %s script + config to %s" %(self.params.resolver, self.params.ip))
        self.remote_copy("rsync", os.path.join(self.params.config, self.params.resolver+"-conf"), self.params.ip+":"+self.tmp, "-r")

        ## Send scripts (cleaner and resolver starter)
        self.remote_copy(program="rsync", from_location=os.path.join(self.params.script_folder, "cleaner.sh"), to_location=self.params.ip+":"+self.tmp)                
        self.remote_copy(program="rsync", from_location=os.path.join(self.params.script_folder, self.params.resolver+".sh"), to_location=self.params.ip+":"+self.tmp)
        
        log.info("Generate config %s" % self.params.resolver)
        self.generate_resolver_config(self.params.resolver, self.params.ip, self.params.port, local_ip)            
        
        log.info("Starting %s" % self.params.resolver)
        #First make sure, that there is no resolver running at needed port
        self.kill_resolver(self.params.ip, self.params.port, self.params.ip)            
        if self.params.resolver == "knot":
            #TODO: this just kill knot maintain port - if you uncomment - you need to add another parameter for this port
            # and also uncomment in /script/knot.sh line with maintain port
            #self.kill_resolver(self.params.ip, self.params.knot_maintain_port, "0.0.0.0")
            #TODO: possible to pick up branch for knot, not just master!
            command = "bash %s %s" % (os.path.join(self.tmp, self.params.resolver+".sh"), "master")
            rv = self.remote_command("ssh", self.params.ip, command)
            self.params.knot_commit = rv.strip()   
            log.info("Knot Branch, commit: %s, %s" % ("master", self.params.knot_commit))     
        else:
            command = "bash %s" % (os.path.join(self.tmp, self.params.resolver+".sh"))
            self.remote_command("ssh", self.params.ip, command)
    
    def kill_resolver(self, server, port, run_ip):
        log.info("sudo bash %s %s %s" % (os.path.join(self.tmp, "cleaner.sh"), run_ip, port))
        command = "sudo bash %s %s %s" % (os.path.join(self.tmp, "cleaner.sh"), run_ip, port)
        self.remote_command("ssh", server, command)            
            
    def generate_resolver_config(self, resolver, server, port, local_ip):
        log.info("Generating %s config" % resolver)
        command = "bash %s %s %s %s" % (os.path.join(self.tmp,resolver+"-conf",resolver+"-conf-generator.sh"), server, port, local_ip)
        self.remote_command("ssh", server, command)        
            
    @staticmethod
    def remote_command(program, ip, command):
        log.info("%s %s %s" % (program, ip, command))
        ssh = subprocess.Popen([program, ip, command],
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
        ssh.wait()        
        retcode = ssh.returncode
        if retcode == 1:
            raise IOError("Cannot execute: %s." % command)
        
        try:
            retval = ssh.stdout.readlines()[0]
        except IndexError:
            raise IOError("Connection failed: %s" % command)
        log.debug("Command done.")
        return retval
    
    @staticmethod
    def remote_copy(program, from_location, to_location, param=None):        
        if not param:
            param = ""
        log.info("%s %s %s %s", program, param, from_location, to_location)
        with open(os.devnull, 'w') as FNULL:    
            ssh = subprocess.Popen([program, param, from_location, to_location],
            shell=False,
            stdout=FNULL,
            stderr=FNULL)
            ssh.wait()
            ssh.communicate()[0]
            if ssh.returncode == 1:
                raise IOError("Cannot execute: %s %s %s %s." %(program, param, from_location, to_location))
        log.debug("Copy done.")
    
    @staticmethod
    def get_ip_address(ifname):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            return socket.inet_ntoa(fcntl.ioctl(
                s.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack('256s', ifname[:15])
            )[20:24])
        except IOError as e:
            log.error("Something wrong with given interface: %s."%ifname)
            raise e