#This file is part jasper_reports module for Tryton.
#The COPYRIGHT file at the top level of this repository contains
#the full copyright notices and license terms.
import os
import re
import time
import tempfile
import logging
from urlparse import urlparse
from PyPDF2 import PdfFileMerger, PdfFileReader
from cStringIO import StringIO

from trytond.report import Report
from trytond.config import config as config_
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.cache import Cache

import JasperReports

# Determines the port where the JasperServer process should listen with its
# XML-RPC server for incomming calls
PORT = config_.getint('jasper', 'port', default=8090)

# Determines the file name where the process ID of the JasperServer
# process should be stored
PID = config_.get('jasper', 'pid', default='tryton-jasper.pid')

# Determines if temporary files will be removed
UNLINK = config_.getboolean('jasper', 'unlink', default=True)

logger = logging.getLogger(__name__)


class JasperReport(Report):
    _get_report_file_cache = Cache('jasper_report.report_file')

    @classmethod
    def write_properties(cls, filename, properties):
        text = u''
        for key, value in properties.iteritems():
            if not value:
                value = key
            key = key.replace(':', '\\:').replace(' ', '\\ ')
            value = value.replace(':', '\\:').replace(' ', '\\ ')
            text += u'%s=%s\n' % (key, value)
        import codecs
        f = codecs.open(filename, 'w', 'latin1')
        #f = open(filename, 'w')
        try:
            f.write(text)
        finally:
            f.close()

    @classmethod
    def get_report_file(cls, report, path=None):
        cache_path = cls._get_report_file_cache.get(report.id)
        if cache_path is not None:
            if (os.path.isfile(cache_path)
                    and (not path or cache_path.startswith(path))):
                return cache_path

        if not path:
            path = tempfile.mkdtemp(prefix='trytond-jasper-')

        report_content = str(report.report_content)
        report_names = [report.report_name]

        # Get subreports in main report
        # <subreportExpression>
        # <![CDATA[$P{SUBREPORT_DIR} + "report_name.jrxml"]]>
        # </subreportExpression>
        e = re.compile('<subreportExpression>.*</subreportExpression>')
        subreports = e.findall(report_content)
        if subreports:
            for subreport in subreports:
                sreport = subreport.split('"')
                report_fname = sreport[1]
                report_name = report_fname[:-7]  # .jasper
                ActionReport = Pool().get('ir.action.report')

                report_actions = ActionReport.search([
                        ('report_name', '=', report_name)
                        ])
                if not report_actions:
                    raise Exception('Error', 'SubReport (%s) not found!' %
                        report_name)
                report_action = report_actions[0]
                cls.get_report_file(report_action, path)
                report_names.append(report_name)

        if not report_content:
            raise Exception('Error', 'Missing report file!')

        fname = os.path.split(report.report)[-1]
        basename = fname.split('.')[0]
        jrxml_path = os.path.join(path, fname)
        f = open(jrxml_path, 'w')
        try:
            f.write(report_content)
        finally:
            f.close()

        Translation = Pool().get('ir.translation')
        translations = Translation.search([
                ('type', '=', 'jasper'),
                ('name', 'in', report_names),
                ], order=[
                ('lang', 'ASC'),
                ])
        lang = None
        p = {}
        for translation in translations:
            if lang != translation.lang:
                if lang:
                    pfile = os.path.join(path, '%s_%s.properties' % (
                            basename, lang.lower()))
                    cls.write_properties(pfile, p)
                    #p.store(open(pfile, 'w'))
                lang = translation.lang
            if translation.src is None or translation.value is None:
                continue
            p[translation.src] = translation.value
        if lang:
            pfile = os.path.join(path, '%s_%s.properties' % (
                    basename, lang.lower()))
            cls.write_properties(pfile, p)
        cls._get_report_file_cache.set(report.id, jrxml_path)
        return jrxml_path

    @classmethod
    def execute(cls, ids, data):
        '''
        Execute the report on record ids.
        The dictionary with data that will be set in local context of the
        report.
        It returns a tuple with:
            report type,
            data,
            a boolean to direct print,
            the report name
        '''
        pool = Pool()
        ActionReport = pool.get('ir.action.report')
        action_reports = ActionReport.search([
                ('report_name', '=', cls.__name__)
                ])
        if not action_reports:
            raise Exception('Error', 'Report (%s) not find!' % cls.__name__)
        cls.check_access()
        action_report = action_reports[0]
        model = action_report.model or data.get('model')
        type, data, pages = cls.render(action_report, data, model, ids)

        if Transaction().context.get('return_pages'):
            return (type, buffer(data), action_report.direct_print,
                action_report.name, pages)

        return (type, buffer(data), action_report.direct_print,
            action_report.name)

    @classmethod
    def render(cls, action_report, data, model, ids):
        logger = logging.getLogger('jasper_reports')

        output_format = action_report.extension
        if 'output_format' in data:
            output_format = data['output_format']

        # Create temporary input (CSV) and output (PDF) files
        temporary_files = []

        fd, dataFile = tempfile.mkstemp()
        os.close(fd)
        fd, outputFile = tempfile.mkstemp()
        os.close(fd)
        temporary_files.append(dataFile)
        temporary_files.append(outputFile)
        logger.info("Temporary data file: '%s'" % dataFile)

        start = time.time()

        report_path = cls.get_report_file(action_report)
        report = JasperReports.JasperReport(report_path)

        # If the language used is xpath create the xmlFile in dataFile.
        if report.language() == 'xpath':
            if data.get('data_source', 'model') == 'records':
                generator = JasperReports.CsvRecordDataGenerator(report,
                    data['records'])
            else:
                generator = JasperReports.CsvBrowseDataGenerator(report, model,
                    ids)
                temporary_files += generator.temporary_files

            generator.generate(dataFile)

        subreportDataFiles = []
        for subreportInfo in report.subreports():
            subreport = subreportInfo['report']
            if subreport.language() == 'xpath':
                message = 'Creating CSV '
                if subreportInfo['pathPrefix']:
                    message += 'with prefix %s ' % subreportInfo['pathPrefix']
                else:
                    message += 'without prefix '
                message += 'for file %s' % subreportInfo['filename']
                logger.info(message)

                fd, subreportDataFile = tempfile.mkstemp()
                os.close(fd)
                subreportDataFiles.append({
                    'parameter': subreportInfo['parameter'],
                    'dataFile': subreportDataFile,
                    'jrxmlFile': subreportInfo['filename'],
                })
                temporary_files.append(subreportDataFile)

                if subreport.isHeader():
                    generator = JasperReports.CsvBrowseDataGenerator(subreport,
                        'res.users', [Transaction().user])
                elif data.get('data_source', 'model') == 'records':
                    generator = JasperReports.CsvRecordDataGenerator(subreport,
                        data['records'])
                else:
                    generator = JasperReports.CsvBrowseDataGenerator(subreport,
                        model, ids)
                generator.generate(subreportDataFile)

        # Start: Report execution section
        locale = Transaction().language

        connectionParameters = {
            'output': output_format,
            'csv': dataFile,
            'dsn': cls.dsn(),
            'user': cls.userName(),
            'password': cls.password(),
            'subreports': subreportDataFiles,
        }
        sources_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)),
            '..', os.path.dirname(action_report.report)) + os.sep
        parameters = {
            'STANDARD_DIR': report.standardDirectory(),
            'REPORT_LOCALE': locale,
            'IDS': ids,
            'SOURCES_DIR': sources_dir,
            'SUBREPORT_DIR': os.path.dirname(report_path) + os.path.sep,
            'REPORT_DIR': os.path.dirname(report_path),
        }
        if 'parameters' in data:
            parameters.update(data['parameters'])

        # Call the external java application that will generate the PDF
        # file in outputFile
        server = JasperReports.JasperServer(PORT)
        server.setPidFile(PID)
        pages = server.execute(connectionParameters, report_path,
            outputFile, parameters)
        # End: report execution section

        elapsed = (time.time() - start) / 60
        logger.info("Elapsed: %.4f seconds" % elapsed)

        # Read data from the generated file and return it
        f = open(outputFile, 'rb')
        try:
            file_data = f.read()
        finally:
            f.close()

        # Remove all temporary files created during the report
        if UNLINK:
            for file in temporary_files:
                try:
                    os.unlink(file)
                except os.error:
                    logger.warning("Could not remove file '%s'." % file)

        return (output_format, file_data, pages)

    @classmethod
    def dsn(cls):
        uri = urlparse(config_.get('database', 'uri'))
        scheme = uri.scheme or 'postgresql'
        host = uri.hostname or 'localhost'
        port = uri.port or 5432
        dbname = Transaction().cursor.dbname
        return 'jdbc:%s://%s:%s/%s' % (scheme, host, str(port), dbname)

    @classmethod
    def userName(cls):
        uri = urlparse(config_.get('database', 'uri'))
        return uri.username or cls.systemUserName()

    @classmethod
    def password(cls):
        uri = urlparse(config_.get('database', 'uri'))
        return uri.password or ''

    @classmethod
    def systemUserName(cls):
        if os.name == 'nt':
            import win32api
            return win32api.GetUserName()
        else:
            import pwd
            return pwd.getpwuid(os.getuid())[0]

    @classmethod
    def path(cls):
        return os.path.abspath(os.path.dirname(__file__))

    @classmethod
    def addonsPath(cls):
        return os.path.dirname(cls.path())

    @classmethod
    def merge_pdfs(cls, pdfs_data):
        merger = PdfFileMerger()
        for pdf_data in pdfs_data:
            tmppdf = StringIO(pdf_data)
            merger.append(PdfFileReader(tmppdf))
            tmppdf.close()

        tmppdf = StringIO()
        merger.write(tmppdf)
        pdf_data = tmppdf.getvalue()

        merger.close()
        tmppdf.close()

        return pdf_data
