import re
from datetime import datetime

from odoo import models, fields, api, exceptions
import logging

from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class SalespersonOrder(models.Model):
    _name = 'idil.salesperson.place.order'
    _description = 'Salesperson Place Order'

    salesperson_id = fields.Many2one('idil.sales.sales_personnel', string='Salesperson', required=True)
    order_date = fields.Datetime(string='Order Date', default=fields.Datetime.now)
    order_lines = fields.One2many('idil.salesperson.place.order.line', 'order_id', string='Order Lines')
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')], default='draft')

    @api.model
    def create(self, vals):
        # Check if the salesperson already has an active draft order
        existing_draft_order = self.search([
            ('salesperson_id', '=', vals.get('salesperson_id')),
            ('state', '=', 'draft'),
        ], limit=1)

        if existing_draft_order:
            # If an active draft order exists, prevent creation of a new one
            raise UserError(
                "This salesperson already has an active draft order. "
                "Please edit the existing order or change its state before creating a new one.")

        # If no active draft order exists, proceed with creating the new order
        return super(SalespersonOrder, self).create(vals)

    def action_confirm_order(self):
        # Additional logic can be added here, like stock availability checks, etc.
        self.write({'state': 'confirmed'})


class SalespersonOrderLine(models.Model):
    _name = 'idil.salesperson.place.order.line'
    _description = 'Salesperson Place Order Line'

    order_id = fields.Many2one('idil.salesperson.place.order', string='Salesperson Order')
    product_id = fields.Many2one('my_product.product', string='Product', required=True)
    quantity = fields.Float(string='Quantity', default=1.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.quantity = 1.0

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError("Quantity must be greater than zero.")
