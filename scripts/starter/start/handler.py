'''
Created on May 25, 2017

@author: Jan Holusa
'''
import params
import maintain
import logging
log = logging.getLogger()
   
class Handler(object):
    '''
    Main program handler.
    '''
    def __init__(self):
        self.params= None
    
    def start(self):
        form='%(asctime)-15s %(levelname)s - %(message)s'
        logging.basicConfig(level=logging.DEBUG, filename="logfile.log", format=form)
        self.params = params.Params() 
        #load parameters    
        try:
            self.params.read_params()
        except IOError as e:
            log.error(e)
            raise
        
        #Prepare remote servers
        self.maintainer = maintain.MaintainResolver(self.params)
        
        if self.params.kill_flag:
            self.maintainer.kill_resolver(self.params.ip, self.params.port, self.params.ip)
        else:
            self.maintainer.prepare_resolvers()
            
        self.params.check_server(self.params.ip, self.params.port)