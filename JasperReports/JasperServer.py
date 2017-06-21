# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
import glob
import time
import socket
import subprocess
import xmlrpclib
import logging

from trytond.config import config
import trytond.error


class JasperServer(trytond.error.WarningErrorMixin):
    def __init__(self, port=8090):
        self.port = port
        self.pidfile = None
        url = 'http://localhost:%d' % port
        self.proxy = xmlrpclib.ServerProxy(url, allow_none=True)

        self._error_messages = {
                'jasper-error': 'Jasper Reports Error: %s',
                }

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
        for font_path in fonts_classpath.split(','):
            font_path = font_path.strip()
            if font_path.endswith('.jar'):
                fonts_classpath += font_path + sep
            else:
                font_path = os.path.join(font_path, '*.jar')
                fonts_classpath += sep.join(glob.glob(font_path))
                if fonts_classpath and not fonts_classpath.endswith(':'):
                    fonts_classpath += ':'

        env['CLASSPATH'] = (os.path.join(self.path(), '..', 'java' + sep) +
            sep.join(glob.glob(libs)) + sep + fonts_classpath +
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
            unicode(self.port),
            ]
        process = subprocess.Popen(command, env=env, cwd=cwd, close_fds=True)
        if self.pidfile:
            f = open(self.pidfile, 'w')
            try:
                f.write(str(process.pid))
            finally:
                f.close()

    def execute(self, *args):
        """
        Render report and return the number of pages generated.
        """
        try:
            return self.proxy.Report.execute(*args)
        except (xmlrpclib.ProtocolError, socket.error), e:
            self.start()
            for x in xrange(40):
                time.sleep(1)
                try:
                    return self.proxy.Report.execute(*args)
                except (xmlrpclib.ProtocolError, socket.error), e:
                    self.error("EXCEPTION: %s %s" % (str(e), str(e.args)))
                    pass
                except xmlrpclib.Fault, e:
                    self.error("EXCEPTION: %s %s" % (str(e), str(e.args)))
                    raise
        except xmlrpclib.Fault, e:
            raise
