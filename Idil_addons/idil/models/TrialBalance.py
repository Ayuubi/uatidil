from datetime import datetime

from odoo import models, fields, api, exceptions
from odoo.exceptions import UserError, ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class TrialBalance(models.Model):
    _name = 'idil.trial.balance'
    _description = 'Trial Balance'

    account_number = fields.Many2one('idil.chart.account', string='Account Number')
    header_name = fields.Char(string='Account Type')
    dr_balance = fields.Float(string='Dr')
    cr_balance = fields.Float(string='Cr')

    label = fields.Char(string='Label', compute='_compute_label')

    @api.depends('account_number', 'dr_balance', 'cr_balance')
    def _compute_label(self):
        for record in self:
            if not record.account_number:
                record.label = 'Grand Total'

            else:
                record.label = ''
