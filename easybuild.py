#!/usr/bin/python

import os 
import re
import time
from distutils.version import LooseVersion

ANSIBLE_METADATA = {
    'metadata_version': '1.21',
    'status': ['preview'],
    'supported_by': 'olivier.mattelaer@uclouvain.be'
}

DOCUMENTATION = '''
---


short_description: This is a module to ease the installation of package with easybuild

version_added: "2.4"

description:
    - "This is a module to ease the installation of package with easybuild"

options:
    name:
        description:
            - This is the message to send to the sample module
        required: true
    new:
        description:
            - Control to demo if the result of this module is changed or not
        required: false

author:
    - olivier.mattelaer@uclouvain.be
'''

EXAMPLES = '''

# (minimal) standard use of easybuild
- easybuild: name/path of the easyconfig file (should follow standard convention) 
  installpath_modules: path where to install the modules (needed to check if nothing has to be done)

# example with full parameter
- package: name/path of the easyconfig file (should follow standard convention) 
  installpath_modules: path where to install the modules (needed to check if nothing has to be done)
  installpath_software: path where to install the software
  installpath_source: path where to install the source
  robot: (default:True) to activate '--robot' option
  force: (default:False) run eb command even if the module is already found in the correct path.
  keep_std: (default:False) keep stdout/stderr for sucessfull completion
  additional_options: add aditional options to eb command. Note that command changing name to the create module requires "force" options
   module_path: force module path
'''

RETURN = '''
returncode: 
    description: returncode of the eb program (0 if not run)
    type: int
message:
    description: some status report of the ansible module
    type: str
stdout:
    description: stdout of the eb process (not fill if retruncode is zero)
    type: str
stderr:
    description: stderr of the eb process (not fill if retruncode is zero)
    type: str
'''

import os
import subprocess
from ansible.module_utils.basic import AnsibleModule

# to allow to use easybuild as an API, you need to do something like
import easybuild
from easybuild.tools.options import set_up_configuration; 
os.chdir('/tmp')
set_up_configuration(silent=True)

def run_module():
    # define the available arguments/parameters that a user can pass to
    # the module
    
    
    module_args = dict(
        package=dict(type='str', required=False, default=''),
        installpath_modules=dict(type='str', required=True),
        installpath_software=dict(type='str', required=False, default=''),
        installpath_source=dict(type='str', required=False, default=''),
        buildpath=dict(type='str', required=False, default=''),
        robot=dict(type='bool',required=False, default=True),
        additional_options=dict(type='str', required=False, default=''),
        force=dict(type='bool', required=False, default=False),
        keep_std=dict(type='bool', required=False, default=False),
        # if the following is True use eb to get the eb package correct.
        search_eb=dict(type='bool', required=False, default=False),
        search_package=dict(type='str', required=False, default=''),
        search_version=dict(type='str', required=False, default=''),
        search_toolchain=dict(type='str', required=False, default=''),
        strict_search=dict(type='bool', required=False, default=False),
        special_edit=dict(type='str', required=False, default=''),
        special_edit_parameters=dict(type='str', required=False, default=''),
        # handling of the cluster
        use_cluster=dict(type='bool', required=False, default=True),
        fetch=dict(type='bool', required=False, default=False),
#        module_path=dict(type='str', required=False, default=''),
        )

    # seed the result dict in the object
    # we primarily care about changed and state
    # change is if this module effectively modified the target
    # state will include any data that you want your module to pass back
    # for consumption, for example, in a subsequent task
    result = dict(
        changed=False,
        message='',
        stdout='',
        stderr='',
        #invocation='',
        returncode='0',
        eb_command=''
    )


    # the AnsibleModule object will be our abstraction working with Ansible
    # this includes instantiation, a couple of common attr would be the
    # args/params passed to the execution, as well as if the module
    # supports check mode
    ans_module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True
    )

#    if ans_module.params['module_path']:
#        import os
#        os.environ['MODULEPATH'] = ans_module.params['module_path']


    eb_name = ans_module.params['package']
    if (eb_name.startswith('./') or eb_name.count('/') > 1) and \
            eb_name.endswith('.eb') and \
            not os.path.exists(eb_name):
        # the file should have been moved to the eb_repo which is in the robot path
        if ans_module.params['robot']:
            eb_name = eb_name.rsplit('/',1)[1]

    otherargs = ans_module.params['additional_options']
    eb_name_for_search = eb_name

    search_eb = ans_module.params['search_eb']
    edit_eb_config = ans_module.params['special_edit']
    if search_eb and edit_eb_config:
        return ans_module.fail_json(msg='eb program failed', **result)        
    #
    #  Searching how to create the easyconfig (bypass built-in eb method)
    #
    if search_eb:
        search_package = ans_module.params['search_package']
        search_version = ans_module.params['search_version']
        search_toolchain = ans_module.params['search_toolchain']
        strict_search = ans_module.params['strict_search']
        
        eb_name, eb_name_for_search, const = search_eb_module(search_package, search_toolchain, search_version, ans_module.params)
        if not eb_name:
            result['skipped'] = True
            ans_module.exit_json(**result)            
        otherargs+=' ' + ' '.join(const)
    #
    #   Handling special function to edit the easyconfig file.
    #
    elif edit_eb_config:
        eb_name, new_eb_name_for_search = eval('%s(ans_module.params)' % edit_eb_config)
        if new_eb_name_for_search:
            eb_name_for_search = new_eb_name_for_search
        if not eb_name:
            ans_module.fail_json(msg='eb program failed', **result)

    modpath = ans_module.params['installpath_modules']
    force_eb = ans_module.params['force']
#    if isinstanceos.path.exists(os.path.join(ans_module.params['robot'],eb_name)):
#        eb_name = os.path.join(ans_module.params['robot'],eb_name)
    
    # check if we need to do any change.
    #  TODO: use easybuild to get the place where module are written
    #        or event better use eb routine to check if the module need change
    #  currently force that path as input and check if the module exists.
    
    # replace the first "-" by a "/" and remove .eb to pass from eb name 
    #to  module name 
    if eb_name_for_search.endswith('.eb'):
        mod_name = eb_name_for_search[:-3]
    else:
        mod_name = eb_name_for_search
    if '/' in mod_name:
        mod_name = mod_name.rsplit('/',1)[1]
    mod_name = mod_name.split("-",1)

    import easybuild.tools.modules as modules
    #import easybuild.tools.config as config
    #config.build_option()
        #config.init_build_options()
    if 'MODULEPATH' in os.environ:
        paths = os.environ['MODULEPATH']
        paths = ans_module.params['installpath_modules'] + "/all:" + paths
    else:
        paths=''
        paths = ans_module.params['installpath_modules'] + "/all"
    modhandler = modules.modules_tool(mod_paths=paths.split(':'))
    if not modhandler:
        ans_module.fail_json(msg='Fail to get a module handler', **result)
    elif not modhandler.exist(['/'.join(mod_name)])[0]:
        result['changed'] = True
    else :
        result['message'] = 'module already installed:', str(modhandler.exist(['/'.join(mod_name)]))
        result['log'] = '/'.join(mod_name)

    if force_eb and result['changed'] == False:
        result['changed'] = True
        result['message'] = 'no changed seems needed but forcing to run eb'


    #
    # OTHER PARAMETER
    #
    robot = ans_module.params['robot']
    softpath = ans_module.params['installpath_software']
    instpath = ans_module.params['installpath_source']
    buildpath = ans_module.params['buildpath']  

    keep_std = ans_module.params['keep_std']
    use_fetch = ans_module.params['fetch']

    if not buildpath: #and softpath:
        import socket
        hostname = socket.gethostname() 
        softhome = os.path.expanduser('~soft')
        buildpath = os.path.join(softhome,'build', hostname.split('.')[0])    
        if not os.path.exists(buildpath):
            if not os.path.exists(os.path.join(softhome, 'build')):
                os.mkdir(os.path.join(softhome, 'build'))
            os.mkdir(buildpath)
    
    use_cluster = ans_module.params['use_cluster']
    if use_cluster:
        #
        # use the constraint of slurm to get the name
        #
        import socket
        hostname = socket.gethostname().split('.')[0]
        command = ['sinfo', '-o','%n,%f']
        j = subprocess.Popen(command, stdout=subprocess.PIPE)
        (stdout, _) = j.communicate()
        for line in stdout.split('\n'):
            if hostname in line:
                feature = line.split(',',1)[1]
                break
        myenv = os.environ.copy()
        myenv["SBATCH_CONSTRAINT"] = feature
        myenv["SBATCH_PARTITION"] = "batch,debug"
        command = ['eb', '--job' , '--job-backend=Slurm', '--job-max-walltime=6']
    else:
        myenv = os.environ
        command = ['eb']

    #
    # Build the easybuild command
    #    
    command.append(eb_name)
    if robot:
        command.append('--robot=%s/../sources/eb_files:%s/../sources/eb_files' % (modpath, modpath.replace('/sw/','/cecisw/')))
        command.append('--robot-path=%s/../sources/eb_files:%s/../sources/eb_files:/usr/easybuild/easyconfigs' % (modpath, modpath.replace('/sw/','/cecisw/')))
    if modpath:
        command.append('--installpath-modules=%s' % modpath)
    if softpath:
        command.append('--installpath-software=%s' % softpath)
    if instpath:
        command.append('--sourcepath=%s' % instpath)
    if buildpath:
        command.append('--buildpath=%s' % buildpath)
    if fetch:
        command.append('--fetch')
    if otherargs:
        command += otherargs.split()


    #
    # store the eb command for debugging/documentation 
    # 
    result['eb_command'] = ' '.join(command)


    # if the user is working with this module in only check mode we do not
    # want to make any changes. So return here
    if ans_module.check_mode:
        result['changed']=False
        print result
        ans_module.exit_json(**result)
        return result
    elif result['changed'] == False:
        return ans_module.exit_json(**result)
   
    #
    # run easybuild
    #
   
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=myenv)

        
    stdout = p.stdout.read()
    stderr = p.stderr.read()
    result['returncode'] = str(p.returncode)
    # do not keep stdout/stderr if no error occur

    if p.returncode or stderr:
        result['stdout'] = stdout
        result['stderr'] = stderr
        #result['returncode'] = p.returncode
        ans_module.fail_json(msg='eb program failed with returncode %s' % p.returncode, **result)
    elif keep_std:
        result['stdout'] = stdout
        result['stderr'] = stderr

    if use_cluster:
        while 1:
            time.sleep(60)
            username = os.environ.get('USER')
            command = ['squeue', '-u %s' % username,  '-t PENDING', '-o \"%j %f\"']
            p = subprocess.Popen(' '.join(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=myenv, shell=True)
            stdout = p.stdout.read()
            prog_name = os.path.basename(eb_name).split('.')[0]
            check_feature = feature.replace(',', '&')
            for line in stdout.split('\n'):
                if check_feature in line and prog_name in line:
                    break
            else:
                break
        

    #
    # run for the hierachical scheme
    #
    if False:
        for i,entry in enumerate(command):
            if entry.startswith('--installpath-modules='):
                command[i] += '_hierarchical'
                break
            else:
                raise Exception, 'modulepath is mandatory'
                
        command.append('--skip')
        command.append('--rebuild')
        if '--package' in command:
            command.remove('--package')

        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=myenv)
        stdout = p.stdout.read()
        stderr = p.stderr.read()
        result['returncode'] = str(p.returncode)
        # do not keep stdout/stderr if no error occur

        if p.returncode or stderr:
            result['stdout'] += stdout
            result['stderr'] += stderr
            #result['returncode'] = p.returncode
            ans_module.fail_json(msg='eb program failed with returncode %s' % p.returncode, **result)
        elif keep_std:
            result['stdout'] += stdout
            result['stderr'] += stderr



    ans_module.exit_json(**result)

def search_eb_module(program, toolchain, version, mod_opts):
    """find an easyblock for the associate program with the specified tool_chain [in format name,version]
       for the associate version (if specified). 
       If a dedicated easyblock does not exist  (and strict_version is False) find a method to 
       create a custom one via the options --try-toolchain= and/or --try-software-version=
        
       The output is 
          1) the name of the eb_module to use
          2) the name of the eb that we would have to check to see if it is already installed
          3) the additional options to pass to eb to install such package
  
       Note if more that one version is available for such program/tool_chain, it returns 
         1) the one in the sources directory if exists
         2) the latest one of those.
    """

    strict_version = mod_opts['strict_search']
    robot = mod_opts['robot']
    mod_opts = mod_opts

    # usefull function to return the valid eb module from a 
    def eb_search(pattern, mod_opts):

        results = {}
        only_keep = None # if some from softhpath only return those
        cmd = ['eb' , '-S', pattern]
        if mod_opts['robot']:
            softpath = mod_opts['installpath_modules']
            cmd.append('--robot=%s/../sources/eb_files:%s/../sources/eb_files' % (softpath,softpath.replace('/sw/','/cecisw/')))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        #raise Exception, p.stdout.read() + ' '.join(cmd)
        all_lines = []
        for line in p.stdout:
            all_lines.append(line)
            line = line.strip()
            if line.startswith('CFGS'):
                key, path = line.split("=")
                results[key] = []
                if softpath in path:
                    assert not only_keep
                    only_keep = key
                
            if line.startswith('*'):
                split = line.split('/')
                key = split[0].split('$',1)[1].strip()
                name = split[-1]
                results[key].append(name)

            if "ERROR: You seem to be running EasyBuild with root privileges which is not wise, so let's end this here." in line:
                raise Exception, line
        
        if only_keep and results[only_keep]:
            return results[only_keep]
        else:
            return [item for sublist in results.values() for item in sublist]

        return results

    if ',' in toolchain:
        toolchain_name, toolchain_version = toolchain.split(',')
    elif toolchain:
        toolchain_name, v1, v2 = re.split('(\d*)', toolchain ,1)
        toolchain_version = '%s%s' % (v1, v2)
    else:
        toolchain_name = '.*'
        toolchain_version = '.*'

    if version == '':
        pattern = '^%s-.*-%s-%s' % (program, toolchain_name, toolchain_version)
        modules = eb_search(pattern, mod_opts)
        if len(modules)==1:
            return modules[0], modules[0], []
        elif len(modules)>1:
            # need to find the highest version number
            vers= [LooseVersion(i) for i in modules]
            mod = str(max(vers))
            return mod, mod, []
        elif not strict_version:
            # no result try be reducing the toolchain version constraint
            if toolchain_version != '.*':
                mod1, mod2, args = search_eb_module(program, '%s,.*' % toolchain_name, '', mod_opts)
                mod2 = mod2.split('-')
                mod2[3] = toolchain_version
                mod2 = '-'.join(mod2)
                #assert not args
                return mod1, mod2, ['--try-toolchain=%s,%s' % (toolchain_name, toolchain_version)]
            elif toolchain_name != '.*':
                mod1, mod2, args = search_eb_module(program, '.*,.*', '', mod_opts)
                mod2 = mod2.split('-')
                mod2[3] = toolchain_version
                mod2[2] = toolchain_name
                mod2 = '-'.join(mod2)
                return mod1, mod2, ['--try-toolchain=%s,%s' % (toolchain_name, toolchain_version)]
            else:
                return None, None, []
        else:
            return None, None, []

    else:
        pattern = '^%s-%s-%s-%s' % (program, version, toolchain_name, toolchain_version)
        modules = eb_search(pattern, mod_opts)
        if len(modules)==1:
            return modules[0], modules[0], []
        elif len(modules)>1:
            # need to find the highest version number
            vers= [LooseVersion(i) for i in modules]
            mod = str(max(vers))
            return mod, mod, []
        elif not strict_version:
            # no result try be reducing the toolchain version constraint and the version constraint!
            # due to the ordering in LooseVersion we will select the code with the highest version first
            # but try to keep the type of toolchain to starstwith
            mod1, mod2, args = search_eb_module(program, '%s,.*' % toolchain_name, '', mod_opts)
            mod2 = mod2.split('-')
            new_args = []
            has_new_version = False
            has_new_tool = False
            if mod2[1] != version:
                mod2[1] = version
                has_new_version = True
                new_args.append('--try-software-version=%s' % version)
            if mod2[2] != toolchain_name:
                mod2[2] = toolchain_name
                has_new_tool = True
                new_args.append('--try-toolchain=%s,%s' % (toolchain_name, toolchain_version))
            if mod2[3] != toolchain_version:
                mod2[3] = toolchain_version
                if not has_new_tool:
                    has_new_tool = True
                    new_args.append('--try-toolchain=%s,%s' % (toolchain_name, toolchain_version))
            if not has_new_tool:
                new_args += args
            mod2 = '-'.join(mod2)
            return mod1, mod2, new_args
        else:
            return None, None, []
    
    return eb_module, eb_to_check, additional_eb_opts

def get_eb_config_path(eb_to_find, from_ebconfig):
    """return the eb config path"""

    cmd = ['eb' , from_ebconfig, '-Dr']
    pattern_path = r'CFGS(\d*)=(.+)'
    pattern_eb = r' \* \[[x ]\] (.+)(%s)(.*)(\.eb)' % eb_to_find

    results = []

    #print cmd
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    paths = {}
    text = ""
    for line in p.stdout:
        text+=line
        if re.search(pattern_path, line):
            pid, position = re.search(pattern_path, line).groups()
            paths[pid] = position
        if re.search(pattern_eb, line, re.I):
            eb_path = ''.join(re.search(pattern_eb, line, re.I).groups())
            break
    else:
        raise Exception, ' '.join(cmd) + '\n' + text

    if eb_path.startswith('$CFGS'):
        if re.search('\$CFGS(\d*)', eb_path):
            pid = re.search('\$CFGS(\d*)', eb_path).groups()[0]
            eb_path = eb_path.replace('$CFGS%s'%pid, paths[pid])
    #print [eb_path]
    return eb_path


def edit_openmpi_for_slurm(params):

    foss_eb = params['special_edit_parameters']
    # check formatting of input
    if 'foss' not in foss_eb:
        foss_eb = 'foss-%s'% foss_eb
    if not foss_eb.endswith('.eb'):
        foss_eb = '%s.eb'% foss_eb

    openmpi_eb_orig_path = get_eb_config_path('OpenMPI', foss_eb)
    mod_name = os.path.basename(openmpi_eb_orig_path)

    path_source = params['installpath_source']
    if path_source:
        path = '%s/openmpi_for_%s' % (path_source, foss_eb)
    else:
        path = '/tmp/openmpi_for_%s' % (foss_eb)
    if os.path.exists(path):
        return path, mod_name
    out = open(path,'w')


    done = 0
    for line in open(openmpi_eb_orig_path):
        out.write(line)
        if line.strip().startswith(('configopts=', 'configopts =')):
            out.write("configopts += \'--with-slurm --with-pmi=/usr/ --with-pmi-libdir=/usr/lib64 \'\n") 
            done +=1

    if done == 1:
        return path, mod_name
    else:
        return False, mod_name

def special_amend(params):

    opts  = eval(params['special_edit_parameters'])

    name = opts['name']
    toolchain = opts['toolchain']
    add_var = opts['var']
    add_value = opts['value']

    
    if not toolchain.endswith('.eb'):
        toolchain = '%s.eb'% toolchain

    orig_path = get_eb_config_path(name, toolchain)
    mod_name = os.path.basename(orig_path)

    path_source = params['installpath_source']
    if path_source:
        path = '%s/amend_%s' % (path_source, name)
    else:
        path = '/tmp/amend_%s' % (name)
    if os.path.exists(path):
        return path, mod_name

    from shutil import copyfile
    copyfile(orig_path, path)

    out = open(path,'a')
    for key,value in zip(add_var, add_value):
        out.write("%s = %s \n" % (key, value))
    out.close()

    return path, mod_name



def main():
    run_module()

if __name__ == '__main__':
    main()
