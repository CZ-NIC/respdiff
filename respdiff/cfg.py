"""
Configuration parser for respdiff suite.

Read-only.
"""

import configparser
import os

import dns.inet


def ipaddr_check(addr):
    """
    Verify that string addr can be parsed as a IP address and return it.
    Raise otherwise.
    """
    dns.inet.af_for_address(addr)  # raises ValueError if the address is bogus
    return addr


def comma_list(lstr):
    """
    Split string 'a, b' into list [a, b]
    """
    return [name.strip() for name in lstr.split(',')]


def transport_opt(ostr):
    if ostr not in {'udp', 'tcp', 'tls'}:
        raise ValueError('unsupported transport')
    return ostr


# declarative config format description for always-present sections
# dict structure: dict[section name][key name] = (type, required)
_CFGFMT = {
    'sendrecv': {
        'timeout': (float, True),
        'jobs': (int, True),
        'time_delay_min': (float, True),
        'time_delay_max': (float, True),
        'max_timeouts': (int, False),
    },
    'servers': {
        'names': (comma_list, True),
    },
    'diff': {
        'target': (str, True),
        'criteria': (comma_list, True),
    },
    'report': {
        'field_weights': (comma_list, True),
    },
}

# declarative config format description for per-server section
# dict structure: dict[key name] = type
_CFGFMT_SERVER = {
    'ip': (ipaddr_check, True),
    'port': (int, True),
    'transport': (transport_opt, True),
    'graph_color': (str, False),
    'restart_script': (str, False),
}


def cfg2dict_convert(fmt, cparser):
    """
    Convert values from ConfigParser into dict with proper data types.

    Raises ValueError if a mandatory section or key is missing
           and if an extra key is detected.
    """
    cdict = {}
    for sectname, sectfmt in fmt.items():
        sectdict = cdict.setdefault(sectname, {})
        for valname, (valfmt, valreq) in sectfmt.items():
            try:
                if not cparser[sectname][valname].strip():
                    raise ValueError('empty values are not allowed')
                sectdict[valname] = valfmt(cparser[sectname][valname])
            except ValueError as ex:
                raise ValueError('config section [{}] key "{}" has invalid format: '
                                 '{}; expected format: {}'.format(
                                     sectname, valname, ex, valfmt))
            except KeyError:
                if valreq:
                    raise KeyError('config section [{}] key "{}" not found'.format(
                        sectname, valname))
        unsupported_keys = set(cparser[sectname].keys()) - set(sectfmt.keys())
        if unsupported_keys:
            raise ValueError('unexpected keys {} in section [{}]'.format(
                unsupported_keys, sectname))
    return cdict


def cfg2dict_check_sect(fmt, cfg):
    """
    Check non-existence of unhandled config sections.
    """
    supported_sections = set(fmt.keys())
    present_sections = set(cfg.keys()) - {'DEFAULT'}
    unsupported_sections = present_sections - supported_sections
    if unsupported_sections:
        raise ValueError('unexpected config sections {}'.format(
            ', '.join('[{}]'.format(sn) for sn in unsupported_sections)))


def cfg2dict_check_diff(cdict):
    """
    Check if diff target is listed among servers.
    """
    if cdict['diff']['target'] not in cdict['servers']['names']:
        raise ValueError('[diff] target value "{}" must be listed in [servers] names'.format(
            cdict['diff']['target']))


def read_cfg(filename):
    """
    Read config file, convert values, validate data and return dict[section][key] = value.
    """
    # verify the file exists (ConfigParser does not do it)
    if not os.path.isfile(filename):
        raise RuntimeError("Config file {} doesn't exist".format(filename))

    parser = configparser.ConfigParser(
        delimiters='=',
        comment_prefixes='#',
        interpolation=None,
        empty_lines_in_values=False)
    parser.read(filename)

    try:
        # parse things which must be present
        cdict = cfg2dict_convert(_CFGFMT, parser)

        # parse variable server-specific data
        cfgfmt_servers = _CFGFMT.copy()
        for server in cdict['servers']['names']:
            cfgfmt_servers[server] = _CFGFMT_SERVER
        cdict = cfg2dict_convert(cfgfmt_servers, parser)

        # check existence of undefined extra sections
        cfg2dict_check_sect(cfgfmt_servers, parser)
        cfg2dict_check_diff(cdict)
    except ValueError as exc:
        # change type of exception so argument parser doesn't hide the error message
        raise RuntimeError(exc)

    return cdict


if __name__ == '__main__':
    from pprint import pprint
    import sys

    pprint(read_cfg(sys.argv[1]))
