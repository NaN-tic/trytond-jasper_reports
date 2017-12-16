# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import PoolMeta

__all__ = ['ActionReport']


class ActionReport:
    __metaclass__ = PoolMeta
    __name__ = 'ir.action.report'

    @classmethod
    def __setup__(cls):
        super(ActionReport, cls).__setup__()
        cls.template_extension.selection.append(('jrxml', 'Jasper Reports'))
