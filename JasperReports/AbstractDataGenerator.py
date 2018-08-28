# This file is part jasper_reports module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.


class AbstractDataGenerator:
    # Simple function all DataGenerators should implement
    def generate(self, fileName):
        pass
