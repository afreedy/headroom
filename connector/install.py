#!/usr/bin/env python3
"""Install Headroom's connector as a per-user macOS login service."""
import argparse, os, plistlib, shutil, subprocess, sys
from pathlib import Path

LABEL = 'com.afreedy.headroom'

def install(origin):
    if sys.platform != 'darwin': raise SystemExit('Automatic startup currently supports macOS.')
    from urllib.parse import urlparse
    u=urlparse(origin)
    if u.scheme not in ('https','http') or not u.netloc or u.path not in ('','/'):
        raise SystemExit('Pass a dashboard origin, without a path.')
    data=Path.home()/'Library/Application Support/Headroom'
    app=data/'app'; app.mkdir(parents=True,exist_ok=True,mode=0o700)
    for name in ('server.py','warmup.py'):
        shutil.copy2(Path(__file__).parent/name,app/name)
    agents=Path.home()/'Library/LaunchAgents';agents.mkdir(exist_ok=True)
    path=agents/(LABEL+'.plist')
    job={'Label':LABEL,'ProgramArguments':[sys.executable,str(app/'server.py'),'--origin',origin.rstrip('/')],
         'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'ProcessType':'Background',
         'WorkingDirectory':str(app),'StandardOutPath':str(data/'connector.log'),'StandardErrorPath':str(data/'connector-error.log'),
         'EnvironmentVariables':{'PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin'},'Umask':0o077}
    path.write_bytes(plistlib.dumps(job));path.chmod(0o600)
    domain=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootout',domain+'/'+LABEL],capture_output=True)
    subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
    print('Headroom now starts at login and restarts automatically. No Codex automation is used.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--origin',required=True)
    install(parser.parse_args().origin)
