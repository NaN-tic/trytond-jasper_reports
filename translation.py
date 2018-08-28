# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import re
from xml import dom
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta

__all__ = [
    'ReportTranslationSet',
    'TranslationClean',
    ]


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

    def extract_report_jrxml(self, content):
        document = dom.minidom.parseString(content)
        return self._translate_jasper_report(document)


class TranslationClean:
    __metaclass__ = PoolMeta
    __name__ = 'ir.translation.clean'

    @staticmethod
    def _clean_jasper(translation):
        Report = Pool().get('ir.action.report')

        with Transaction().set_context(active_test=False):
            # TODO: Clean strings that no more exists in the report?
            if not Report.search([
                        ('report_name', '=', translation.name),
                        ]):
                return True
