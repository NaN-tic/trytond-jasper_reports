# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from xml import dom
import copy
import os
import re

from trytond.wizard import Wizard
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond.tools import file_open
from difflib import SequenceMatcher

__all__ = [
    'Translation',
    'ReportTranslationSet',
    'TranslationUpdate',
    'TranslationClean',
    ]


class Translation:
    __metaclass__ = PoolMeta
    __name__ = 'ir.translation'

    @classmethod
    def __setup__(cls):
        super(Translation, cls).__setup__()
        new_type = ('jasper', 'Jasper Report')
        if new_type not in cls.type.selection:
            cls.type = copy.copy(cls.type)
            cls.type.selection = copy.copy(cls.type.selection)
            cls.type.selection.append(new_type)

    @property
    def unique_key(self):
        if self.type == 'jasper':
            return (self.name, self.type, self.src)
        return super(Translation, self).unique_key


class ReportTranslationSet:
    __metaclass__ = PoolMeta
    __name__ = "ir.translation.set"

    def _translate_jasper_report(self, node):
        strings = []
        if node.nodeType in (node.CDATA_SECTION_NODE, node.TEXT_NODE):
            if not (node.parentNode and
                    node.parentNode.tagName.endswith('Expression')):
                return []
            if node.nodeValue:
                node_strings = re.findall('tr *\([^\(]*,[ ]*"([^"]*)"\)',
                node.nodeValue)
                strings += [x for x in node_strings if x]

        for child in [x for x in node.childNodes]:
            strings.extend(self._translate_jasper_report(child))
        return strings

    def _store_report_strings(self, report, strings, type_):
        Translation = Pool().get('ir.translation')
        cursor = Transaction().connection.cursor()
        translation = Translation.__table__()

        translations = Translation.search([
                ('lang', '=', 'en'),
                ('type', '=', type_),
                ('name', '=', report.report_name),
                ('module', '=', report.module or ''),
                ])
        trans_reports = {}
        to_create = []
        for trans in translations:
            trans_reports[trans.src] = trans
        for string in {}.fromkeys(strings).keys():
            src_md5 = Translation.get_src_md5(string)
            done = False
            if string in trans_reports:
                del trans_reports[string]
                continue
            for string_trans in trans_reports:
                if string_trans in strings:
                    continue
                seqmatch = SequenceMatcher(lambda x: x == ' ',
                        string, string_trans)
                if seqmatch.ratio() == 1.0:
                    del trans_reports[report.report_name][string_trans]
                    done = True
                    break
                if seqmatch.ratio() > 0.6:
                    cursor.execute(*translation.update(
                            [translation.src, translation.fuzzy,
                                translation.src_md5],
                            [string, True, src_md5],
                            where=(translation.name == report.report_name)
                            & (translation.type == type_)
                            & (translation.src == string_trans)
                            & (translation.module == report.module)))
                    del trans_reports[string_trans]
                    done = True
                    break
            if not done:
                to_create.append({
                        'name': report.report_name,
                        'lang': 'en',
                        'type': type_,
                        'src': string,
                        'module': report.module,
                        })
        if to_create:
            Translation.create(to_create)
        if strings:
            cursor.execute(*translation.delete(
                    where=(translation.name == report.report_name)
                    & (translation.type == type_)
                    & (translation.module == report.module)
                    & ~translation.src.in_(strings)))

    def set_report(self):
        pool = Pool()
        Report = pool.get('ir.action.report')

        result = super(ReportTranslationSet, self).set_report()

        with Transaction().set_context(active_test=False):
            reports = Report.search([('report', 'ilike', '%.jrxml')])

        if not reports:
            return {}

        for report in reports:
            strings = []

            # odt_content = ''
            if report.report:
                with file_open(report.report.replace('/', os.sep),
                        mode='rb') as fp:
                    jasper_content = fp.read()
            for content in (report.report_content_custom, jasper_content):
                if not content:
                    continue
                content_str = str(content) if bytes == str else content.decode()
                document = dom.minidom.parseString(content_str)
                strings += self._translate_jasper_report(document)
            self._store_report_strings(report, strings, 'jasper')
        return result


class TranslationUpdate:
    __metaclass__ = PoolMeta
    __name__ = "ir.translation.update"

    @classmethod
    def __setup__(cls):
        super(TranslationUpdate, cls).__setup__()
        if 'jasper' not in cls._source_types:
            cls._source_types.append('jasper')


class TranslationClean(Wizard):
    "Clean translation"
    __name__ = 'ir.translation.clean'

    @staticmethod
    def _clean_jasper(translation):
        pool = Pool()
        Report = pool.get('ir.action.report')
        with Transaction().set_context(active_test=False):
            # TODO: Clean strings that no more exists in the report?
            if not Report.search([
                        ('report_name', '=', translation.name),
                        ]):
                return True
