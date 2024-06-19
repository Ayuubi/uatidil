from odoo import models, fields


class CustomAccountingEntry(models.Model):
    _name = 'custom.accounting.entry'
    _description = 'Custom Accounting Entry'

    pos_order_id = fields.Many2one('pos.order', string='POS Order Reference')
    amount_paid = fields.Float(string='Amount Paid')
    amount_total = fields.Float(string='Total Amount')
    amount_tax = fields.Float(string='Tax Amount')
