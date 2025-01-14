# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import os
import re
import time
import tempfile
import logging
import subprocess
import xmlrpc
import zipfile
from io import BytesIO
from urllib.parse import urlparse
from pypdf import PdfReader, PdfWriter
from trytond.report import Report
from trytond.report.report import TranslateFactory
from trytond.config import config as config_
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.cache import Cache
from trytond.modules import MODULES_PATH
from trytond.tools import slugify
from trytond.exceptions import UserError

from .JasperReports import JasperReport as JReport, JasperServer
from .JasperReports import CsvRecordDataGenerator, CsvBrowseDataGenerator

# Determines the port where the JasperServer process should listen with its
# XML-RPC server for incomming calls
PORT = config_.getint('jasper', 'port', default=8090)

# Determines the file name where the process ID of the JasperServer
# process should be stored
PID = config_.get('jasper', 'pid', default='tryton-jasper.pid')

# Determines if temporary files will be removed
UNLINK = config_.getboolean('jasper', 'unlink', default=True)

# Determines whether report path cache should be used or not
USE_CACHE = config_.getboolean('jasper', 'use_cache', default=True)
CACHE_FOLDER = config_.get('jasper', 'cache_folder', default=None)

# Determines if on merge, resulting PDF should be compacted using ghostscript
COMPACT_ON_MERGE = config_.getboolean('jasper', 'compact_on_merge',
    default=False)

REDIRECT_MODEL = config_.get('jasper', 'redirect_model')

logger = logging.getLogger(__name__)


class JasperReport(Report):
    _get_report_file_cache = Cache('jasper_report.report_file')

    @classmethod
    def write_properties(cls, filename, properties):
        def display_unicode(data):
            return "".join(["\\u%s" % hex(ord(x))[2:].zfill(4) for x in data])

        with open(filename, 'w') as f:
            for key, value in properties.items():
                if not value:
                    value = key
                key = display_unicode(key)
                value = display_unicode(value)
                f.write('%s=%s\n' % (key, value))

    @classmethod
    def get_report_file(cls, report, path=None):
        pool = Pool()
        Lang = pool.get('ir.lang')
        Translation = pool.get('ir.translation')

        if USE_CACHE:
            cache_path = cls._get_report_file_cache.get(report.id)
            if cache_path is not None:
                if (os.path.isfile(cache_path)
                        and (not path or cache_path.startswith(path))):
                    return cache_path

        if not path:
            if CACHE_FOLDER:
                if not os.path.exists(CACHE_FOLDER):
                    os.makedirs(CACHE_FOLDER)
                path = CACHE_FOLDER
            else:
                path = tempfile.mkdtemp(prefix='trytond-jasper-')

        report_content = report.report_content
        report_names = [report.report_name]

        # Get subreports in main report
        # <subreportExpression>
        # <![CDATA[$P{SUBREPORT_DIR} + "report_name.jrxml"]]>
        # </subreportExpression>
        e = re.compile('<subreportExpression>.*?</subreportExpression>')
        subreports = e.findall(str(report_content))
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

        fname = os.path.split(report.report or '')[-1]
        basename = fname.split('.')[0]
        jrxml_path = os.path.join(path, fname)
        f = open(jrxml_path, 'wb')
        try:
            f.write(report_content)
        finally:
            f.close()

        # TODO known all keys by report
        keys = set(t.src for t in Translation.search([
                    ('name', '=', report.report_name),
                    ('type', '=', 'report'),
                    ]))

        for lang in Lang.search([('translatable', '=', True)]):
            with Transaction().set_context(language=lang.code):
                translate = TranslateFactory(cls.__name__, Translation)

                properties = dict()
                for key in keys:
                    properties[key] = translate(key)

                pfile = os.path.join(path, '%s_%s.properties' % (
                        basename, lang.code.lower()))
                cls.write_properties(pfile, properties)

        cls._get_report_file_cache.set(report.id, jrxml_path)
        return jrxml_path

    @classmethod
    def get_action(cls, data):
        pool = Pool()
        ActionReport = pool.get('ir.action.report')

        action_id = data.get('action_id')
        if action_id is None:
            action_reports = ActionReport.search([
                    ('report_name', '=', cls.__name__)
                    ])
            assert action_reports, '%s not found' % cls
            action = action_reports[0]
        else:
            action = ActionReport(action_id)

        return action, action.model or data.get('model')

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

        action_report, model = cls.get_action(data)
        cls.check_access(action_report, model, ids)

        # Limit the filename to 40 chars to ensure that Windows and
        # Windows Office could open the file correctly. In general accept
        # only 255 chars or less for the path + filename.
        action_name = slugify(action_report.name)[:40]

        # report single and len > 1, return zip file
        if action_report.single and len(ids) > 1:
            Model = pool.get(model)
            records = Model.browse(ids)
            rec_names = dict((x.id, x) for x in records)
            suffix = '-'.join(r.rec_name for r in records[:5])
            filename = slugify('%s-%s' % (action_name, suffix))
            filename = filename[:40]
            content = BytesIO()
            with zipfile.ZipFile(content, 'w') as content_zip:
                for id in ids:
                    type, rcontent, _ = cls.render(action_report, data, model,
                        [id])
                    rfilename = '%s-%s' % (
                        slugify(action_name),
                        slugify(rec_names[id].rec_name))
                    rfilename = '%s.%s' % (rfilename[:40], type)
                    content_zip.writestr(rfilename, rcontent)
            content = content.getvalue()
            return ('zip', content, False, filename)

        try:
            type, data, pages = cls.render(action_report, data, model, ids)
        except xmlrpc.client.Fault as e:
            raise UserError(str(e))

        if Transaction().context.get('return_pages'):
            return (type, bytearray(data), action_report.direct_print,
                action_report.name, pages)

        if REDIRECT_MODEL:
            Printer = None
            try:
                Printer = pool.get(REDIRECT_MODEL)
            except KeyError:
                logger.warning('Redirect model "%s" not found.',
                    REDIRECT_MODEL)

            if Printer:
                return Printer.send_report(type, bytearray(data),
                    action_name, action_report)

        return (type, bytearray(data), action_report.direct_print, action_name)

    @classmethod
    def render(cls, action_report, data, model, ids):
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
        report = JReport(report_path)

        # If the language used is xpath create the xmlFile in dataFile.
        if report.language() == 'xpath':
            if data.get('data_source', 'model') == 'records':
                generator = CsvRecordDataGenerator(report, data['records'])
            else:
                generator = CsvBrowseDataGenerator(report, model, ids)
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
                    generator = CsvBrowseDataGenerator(subreport,
                        'res.users', [Transaction().user])
                elif data.get('data_source', 'model') == 'records':
                    generator = CsvRecordDataGenerator(subreport,
                        data['records'])
                else:
                    generator = CsvBrowseDataGenerator(subreport, model, ids)
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
        sources_dir = os.path.join(
            MODULES_PATH,
            os.path.dirname(action_report.report) + os.sep)
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
        server = JasperServer(PORT)
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
        dbname = Transaction().database.name
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
        merger = PdfWriter()
        for pdf_data in pdfs_data:
            tmppdf = BytesIO(pdf_data)
            merger.append(PdfReader(tmppdf))
            tmppdf.close()

        if COMPACT_ON_MERGE:
            # Use ghostscript to compact PDF which will usually remove
            # duplicated images. It can make a PDF go from 17MB to 1.8MB,
            # for example.
            path = tempfile.mkdtemp()
            merged_path = os.path.join(path, 'merged.pdf')
            merged = open(merged_path, 'wb')
            merger.write(merged)
            merged.close()

            compacted_path = os.path.join(path, 'compacted.pdf')
            # changed PDFSETTINGS from /printer to /prepress
            command = ['gs', '-q', '-dBATCH', '-dNOPAUSE', '-dSAFER',
                '-sDEVICE=pdfwrite', '-dPDFSETTINGS=/prepress',
                '-sOutputFile=%s' % compacted_path, merged_path]
            subprocess.call(command)

            f = open(compacted_path, 'r')
            try:
                pdf_data = f.read()
            finally:
                f.close()
        else:
            tmppdf = BytesIO()
            merger.write(tmppdf)
            pdf_data = tmppdf.getvalue()
            merger.close()
            tmppdf.close()

        return pdf_data
