# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

import os
import csv
import tempfile

from .AbstractDataGenerator import AbstractDataGenerator

from trytond.model import Model
from trytond.pool import Pool
from trytond.transaction import Transaction

import logging


class BrowseDataGenerator(AbstractDataGenerator):
    def __init__(self, report, model, ids):
        self.report = report
        self.model = model
        self.ids = ids
        self._languages = []
        self.imageFiles = {}
        self.temporary_files = []
        self.logger = logging.getLogger('jasper_reports')

    def warning(self, message):
        self.logger.warning(message)

    def languages(self):
        if self._languages:
            return self._languages
        pool = Pool()
        ids = pool.get('ir.lang').search([('translatable', '=', '1')])
        self._languages = [x.code for x in pool.get('ir.lang').browse(ids)]
        return self._languages

    def valueInAllLanguages(self, model, id, field):
        values = {}
        for language in self.languages():
            with Transaction().set_context(language=(language or 'en')):
                values[language] = model.read([id], [field])[0][field] or ''
        result = []
        for key, value in values.items():
            result.append('%s~%s' % (key, value))
        return '|'.join(result)

    def generateIds(self, record, relations, path, currentRecords):
        pool = Pool()
        unrepeated = set([field.partition('/')[0] for field in relations])
        for relation in unrepeated:
            root = relation.partition('/')[0]
            if path:
                currentPath = '%s/%s' % (path, root)
            else:
                currentPath = root
            if root == 'Attachments':
                value = pool.get('ir.attachment').search([
                        ('resource', '=', str(record)),
                        ])
            elif root == 'User':
                value = pool.get('res.user').browse([Transaction().user])
            else:
                try:
                    value = getattr(record, root)
                except AttributeError:
                    self.warning("Field '%s' does not exist in model '%s'." %
                            (root, record.__name__))
                    continue

                if isinstance(value, Model):
                    relations2 = [f.partition('/')[2] for f in relations if
                        f.partition('/')[0] == root and f.partition('/')[2]]
                    return self.generateIds(value, relations2, currentPath,
                            currentRecords)

                if not isinstance(value, (list, tuple)):
                    self.warning("Field '%s' in model '%s' is not a relation."
                            % (root, self.model))
                    return currentRecords

            # Only join if there are any records because it's a LEFT JOIN
            # If we wanted an INNER JOIN we wouldn't check for "value" and
            # return an empty currentRecords
            if value:
                # Only
                newRecords = []
                for v in value:
                    currentNewRecords = []
                    for id in currentRecords:
                        new = id.copy()
                        new[currentPath] = v
                        currentNewRecords.append(new)
                    relations2 = [f.partition('/')[2] for f in relations
                            if f.partition('/')[0] == root and
                            f.partition('/')[2]]
                    newRecords += self.generateIds(v, relations2, currentPath,
                            currentNewRecords)

                currentRecords = newRecords
        return currentRecords


class CsvBrowseDataGenerator(BrowseDataGenerator):
    # CSV file generation works as follows:
    # By default (if no TRYTON_RELATIONS property exists in the report) a
    # record will be created for each model id we've been asked to show. If
    # there are any elements in the TRYTON_RELATIONS list, they will imply a
    # LEFT JOIN like behaviour on the rows to be shown.
    def generate(self, fileName):
        pool = Pool()

        self.allRecords = []
        relations = self.report.relations()
        # The following loop generates one entry to allRecords list for each
        # record that will be created. If there are any relations it acts like
        # a LEFT JOIN against the main model/table.
        for record in pool.get(self.model).browse(self.ids):
            newRecords = self.generateIds(record, relations, '', [{
                    'root': record
                    }])
            copies = 1
            if self.report.copiesField() and hasattr(record,
                    self.report.copiesField()):
                copies = int(getattr(record, self.report.copiesField()))
            for new in newRecords:
                for x in range(copies):
                    self.allRecords.append(new)

        f = open(fileName, 'w+', encoding='utf-8')
        try:
            csv.QUOTE_ALL = True
            # JasperReports CSV reader requires an extra colon at the end of
            # the line.
            writer = csv.DictWriter(f, self.report.fieldNames() + [''],
                    delimiter=",", quotechar='"')
            header = {}
            for field in self.report.fieldNames() + ['']:
                header[field] = field
            writer.writerow(header)
            # Once all records have been calculated, create the CSV structure
            # itself
            for records in self.allRecords:
                row = {}
                self.generateCsvRecord(records['root'], records, row, '',
                        self.report.fields())
                writer.writerow(row)
        finally:
            f.close()

    def generateCsvRecord(self, record, records, row, path, fields):
        pool = Pool()
        Attachment = pool.get('ir.attachment')
        User = pool.get('res.user')

        # One field (many2one, many2many or one2many) can appear several times.
        # Process each "root" field only once by using a set.
        unrepeated = set([field.partition('/')[0] for field in fields])
        for field in unrepeated:
            if not field:
                continue
            root = field.partition('/')[0]
            if path:
                currentPath = '%s/%s' % (path, root)
            else:
                currentPath = root
            if root == 'Attachments':
                value = Attachment.search([
                        ('resource', '=', str(record)),
                        ])
            elif root == 'User':
                value = User(Transaction().user)
            else:
                try:
                    value = getattr(record, root)
                    field_type = record._fields[field]._type
                except AttributeError:
                    value = None
                    field_type = None
                    self.warning("Field '%s' (path: %s) does not exist in "
                            "model '%s'." % (root, currentPath,
                            record.__name__))

            # Check if it's a many2one
            if isinstance(value, Model):
                fields2 = [f.partition('/')[2] for f in fields if
                        f.partition('/')[0] == root]
                self.generateCsvRecord(value, records, row, currentPath,
                        fields2)
                continue

            # Check if it's a one2many or many2many
            if isinstance(value, (list, tuple)):
                if not value:
                    continue
                fields2 = [f.partition('/')[2] for f in fields
                        if f.partition('/')[0] == root]
                if currentPath in records:
                    self.generateCsvRecord(records[currentPath], records, row,
                            currentPath, fields2)
                else:
                    # If the field is not marked to be iterated use the first
                    # record only
                    self.generateCsvRecord(value[0], records, row,
                            currentPath, fields2)
                continue

            # The field might not appear in the self.report.fields()
            # only when the field is a many2one but in this case it's null.
            # This will make the path to look like: "journal_id", when the
            # field actually in the report is "journal_id/name", for example.
            #
            # In order not to change the way we detect many2one fields, we
            # simply check that the field is in self.report.fields() and that's
            # it.
            if currentPath not in self.report.fields():
                continue

            # Show all translations for a field
            type = self.report.fields()[currentPath]['type']
            if type == 'java.lang.Object':
                value = self.valueInAllLanguages(record, record.id, root)

            # The rest of field types must be converted into str
            if field == 'id':
                # Check for field 'id' because we can't find it's
                # type in _fields
                value = str(value)
            elif value is None:
                value = ''
            elif field_type == 'date':
                value = '%s 00:00:00' % str(value)
            elif field_type == 'binary':
                imageId = (record.id, field)
                if imageId in self.imageFiles:
                    fileName = self.imageFiles[imageId]
                else:
                    fd, fileName = tempfile.mkstemp()
                    try:
                        os.write(fd, value)
                    finally:
                        os.close(fd)
                    self.temporary_files.append(fileName)
                    self.imageFiles[imageId] = fileName
                value = fileName
            elif field_type == 'timedelta':
                value = value.total_seconds()
            elif isinstance(value, float):
                value = '%.10f' % value
            elif not isinstance(value, str):
                value = str(value)
            row[self.report.fields()[currentPath]['name']] = value
