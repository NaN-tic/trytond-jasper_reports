# -*- encoding: utf-8 -*-
# This file is part of jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.wizard import Wizard, StateView, StateTransition, Button

__all__ = ['DataTemplateStart', 'DataTemplateResult', 'DataTemplate']


class DataTemplateStart(ModelView):
    'Create Data Template Start'
    __name__ = 'jasper_reports.data_template.start'
    model = fields.Many2One('ir.model', 'Model', required=True)
    depth = fields.Integer('Depth', required=True)

    @staticmethod
    def default_depth():
        return 3


class DataTemplateResult(ModelView):
    "Data Template Result"
    __name__ = 'jasper_reports.data_template.result'
    file = fields.Binary('File', readonly=True)
    depth = fields.Integer('Depth', required=True)


class DataTemplate(Wizard):
    'Data Template'
    __name__ = 'jasper_reports.data_template'
    start = StateView('jasper_reports.data_template.start',
        'jasper_reports.data_template_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Export', 'export', 'tryton-ok', default=True),
            ])
    export = StateTransition()
    result = StateView('jasper_reports.data_template.result',
        'jasper_reports.data_template_result_view_form', [
            Button('Close', 'end', 'tryton-close'),
            ])

    def transition_export(self):
        pool = Pool()
        Model = pool.get('ir.model')

        model = self.start.model.model
        depth = self.start.depth

        self.result.file = Model.generate_jreport_xml(model, depth)
        return 'result'

    def default_result(self, fields):
        file_ = self.result.file
        self.result.file = False  # No need to store it in session
        return {
            'file': file_,
            }
