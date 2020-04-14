# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
import signal
import glob
import time
import socket
import subprocess
import xmlrpc.client
import logging

from trytond.config import config
from trytond.exceptions import UserWarning


class JasperServer(UserWarning):
    pid = None

    def __init__(self, port=8090):
        self.port = port
        self.pidfile = None
        url = 'http://localhost:%d' % port
        self.proxy = xmlrpc.client.ServerProxy(url, allow_none=True)
        self.logger = logging.getLogger('jasper_reports')

    def error(self, message):
        self.logger.error(message)

    def path(self):
        return os.path.abspath(os.path.dirname(__file__))

    def setPidFile(self, pidfile):
        self.pidfile = pidfile

    def start(self):
        env = {}
        env.update(os.environ)
        if os.name == 'nt':
            sep = ';'
        else:
            sep = ':'

        libs = os.path.join(self.path(), '..', 'java', 'lib', '*.jar')

        fonts_classpath = config.get('jasper', 'fonts_path', default='')
        f_cp = ""
        for font_path in fonts_classpath.split(','):
            font_path = font_path.strip()
            if font_path.endswith('.jar'):
                f_cp += font_path + sep
            else:
                font_path = os.path.join(font_path, '*.jar')
                f_cp += sep.join(glob.glob(font_path))
                if f_cp and not f_cp.endswith(':'):
                    f_cp += ':'

        env['CLASSPATH'] = (os.path.join(self.path(), '..', 'java' + sep) +
            sep.join(glob.glob(libs)) + sep + f_cp +
            os.path.join(self.path(), '..', 'custom_reports'))
        cwd = os.path.join(self.path(), '..', 'java')

        # Set headless = True because otherwise, java may use existing
        # X session and if session is
        # closed JasperServer would start throwing exceptions. So we better
        # avoid using the session at all.
        command = [
            'java',
            '-Djava.awt.headless=true',
            'com.nantic.jasperreports.JasperServer',
            str(self.port),
            ]
        process = subprocess.Popen(command, env=env, cwd=cwd, close_fds=True)
        JasperServer.pid = process.pid
        if self.pidfile:
            with open(self.pidfile, 'w') as f:
                f.write(str(process.pid))

    @staticmethod
    def stop():
        if not JasperServer.pid:
            return
        os.kill(JasperServer.pid, signal.SIGTERM)
        time.sleep(2)
        os.kill(JasperServer.pid, signal.SIGKILL)

    def execute(self, *args):
        """
        Render report and return the number of pages generated.
        """
        try:
            return self.proxy.Report.execute(*args)
        except (xmlrpc.client.ProtocolError, socket.error):
            self.start()
            for x in range(40):
                time.sleep(1)
                try:
                    return self.proxy.Report.execute(*args)
                except (xmlrpc.client.ProtocolError, socket.error) as e:
                    self.error("EXCEPTION: %s %s" % (str(e), str(e.args)))
                    pass
                except xmlrpc.client.Fault as e:
                    self.error("EXCEPTION: %s %s" % (str(e), str(e.args)))
                    raise
        except xmlrpc.client.Fault:
            raise
