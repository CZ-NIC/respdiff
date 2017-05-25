# Overview and usage

## What it roughly does
This python testing tool starts resolvers at servers according the config files.
After that, it starts sending queries to the resolvers and comparing responses. 
Different responses are stored in the result folder.

## What do you need
At the test machine:
* Python2.7
* Python package [dns](http://www.dnspython.org/)
* User named `kresdbench`

At the machine with resolvers:
* Bind, Unbound, Power Dns and Knot-resolver libraries for compiling resolvers from resources
* User named `kresdbench` in `sudo` group

## How to run tests
* Test can be run by command `$python2.7 respdif -c config/config.cfg -i data/dataset`
It uses these optional flags:
* `-s, --case_sensitive` - starts comparing case-sensitive.
* `-d, --debug` - switch log output level from info to debug. 
* `--json` - creates json output.
* `-o, --compare_others` - Compare also other resolvers each to other. Not just kresd to other.
* `-b, --branch` - which branch of Knot Resolver should be used. This option has higher priority than from config file. 

## Input file
Input file can be in two formats:
* First contains on each line number and server to be queried separated
by comma. For example `666,nic.cz`. Example of input file is file `top-1m.csv`.
* Second contains on each line server to be queried and type of query separated
by tabulator. For example `nic.cz	AAAA`.

## Configuration files
### Test configuration
Contains 4 section: general and one section for each resolver. In section general
you can configure these parameters:
* `rdatatype` - list of types to be tested (MX, AAAA, A, NS, ...). Each query will be tested on each
type in the list.
* `rdataclass` - list of classes to be tested (IN, CH, ...). Each query will be tested on each
class in the list.
* `rdata_rdatatype_ignore` - In which type of rdatatype queries should be ignored rdata section in comparison.
* `querries` - how many queries send from the input file.
* `querry_timeout` - timeout for each query.
* `ttl_range` - indicates how benevolent will be ttl comparison.
* `compare_sections` - list of sections to compare (opcode, rcode, flags, answer, ...).
* `local_interface` - Set local interface name. Default is em0. It is necessary for preparing resolvers at server side. 
* `run_under_docker` - Set program to run under docker. if parameter is set to yes different style of saving results is used. 
Possible values are yes and no. Default value is no.
* `result` - results folder where will be created 'date' folders with results.
* `email` - email where to send result summary. In case of differences the readable output is also attached. 

In other three sections named knot, bind, unbound and pdns 
you can use these parameters:
* `port` port where is running particular resolver. 
* `ip` ip address where is running particular resolver.
* `start_remotely` is flag, which indicates start of the server in given ip and port.
Possible values are yes and no. Default is no.
* `branch` name of the knot branch. This parameter is possible to use just in the `knot` section.

Example of configuration file: `config/respdif.cfg`

### Resolver config
Configuration scripts of resolvers are located in the `resolvers_setup` folder. 

## Outputs
Output from the each test is stored in the `result` folder into timestamp folder of the test.
Each timestamp folder contains log file and output file. It is possible to change names of this
files in the file `local_constants.py`. Log file show just results of each sended query 
(OK [just debug mode] - servers return the same response, or NOK - response was not the same). 
Output file show moreover sections of response where was the difference found.