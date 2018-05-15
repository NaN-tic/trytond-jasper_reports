# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import data_template
from . import action
from . import model
from . import translation


def register():
    Pool.register(
        data_template.DataTemplateStart,
        data_template.DataTemplateResult,
        action.ActionReport,
        model.Model,
        module='jasper_reports', type_='model')
    Pool.register(
        data_template.DataTemplate,
        translation.ReportTranslationSet,
        translation.TranslationClean,
        module='jasper_reports', type_='wizard')
