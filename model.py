# -*- coding: utf-8 -*-
# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import sys
import unicodedata
from xml.dom.minidom import getDOMImplementation

from trytond.pool import Pool, PoolMeta

__all__ = ['Model']

src_chars = """ '"()/*-+?Â¿!&$[]{}@#`'^:;<>=~%,\\"""
dst_chars = """________________________________"""
if sys.version_info < (3, 0, 0):
    src_chars = str(src_chars, 'iso-8859-1')
    dst_chars = str(dst_chars, 'iso-8859-1')


class Model(metaclass=PoolMeta):
    __name__ = 'ir.model'

    @staticmethod
    def unaccent(text):
        output = text
        for c in range(len(src_chars)):
            if c >= len(dst_chars):
                break
            output = output.replace(src_chars[c], dst_chars[c])
        output = unicodedata.normalize('NFKD', output).encode('ASCII',
            'ignore')
        return str(output, encoding='utf-8').strip('_')


    @staticmethod
    def generate_jreport_xml(model, depth=1):
        """
        Generate XML from ir.model
        @param model: object
        @param depth: str
        :return file
        """
        IrModel = Pool().get('ir.model')
        document = getDOMImplementation().createDocument(None, 'data', None)
        topNode = document.documentElement
        recordNode = document.createElement('record')
        topNode.appendChild(recordNode)
        IrModel.get_jreport_xml(model, recordNode, document, depth)
        file_data = topNode.toxml()
        return bytes(file_data, encoding='utf-8')

    @staticmethod
    def get_jreport_xml(model, parentNode, document, depth=1, first_call=True):
        """Get data fields XML
        @param model: str
        @param parentNode: object
        @param document: object
        @param depth: str
        @param first_call: boolean
        """
        pool = Pool()
        IrModel = pool.get('ir.model')

        model = IrModel.search([('name', '=', model)])[0]

        fieldNode = document.createElement('id')
        parentNode.appendChild(fieldNode)
        valueNode = document.createTextNode('1')
        fieldNode.appendChild(valueNode)

        for field in model.fields:
            if field.name == 'id':
                continue

            name = IrModel.unaccent(field.name)
            name = '%s-%s' % (name, name)
            fieldNode = document.createElement(name)
            parentNode.appendChild(fieldNode)

            fieldType = field.ttype
            if fieldType in ('many2one', 'one2many', 'many2many'):
                if depth <= 1:
                    continue
                newName = field.relation
                IrModel.get_jreport_xml(newName, fieldNode, document,
                    depth - 1, False)
                continue

        # TODO: Create relation with attachments

        if first_call:
            # Create relation with user
            fieldNode = document.createElement('user-user')
            parentNode.appendChild(fieldNode)
            IrModel.get_jreport_xml('res.user', fieldNode, document,
                depth - 1, False)
