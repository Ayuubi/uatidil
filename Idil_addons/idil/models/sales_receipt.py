from odoo import models, fields
from odoo.exceptions import UserError


class SalesReceipt(models.Model):
    _name = 'idil.sales.receipt'
    _description = 'Sales Receipt'

    sales_order_id = fields.Many2one('idil.sale.order', string='Sale Order', required=True)
    salesperson_id = fields.Many2one('idil.sales.sales_personnel', string='Salesperson',
                                     related='sales_order_id.sales_person_id', store=True, readonly=True)
    receipt_date = fields.Datetime(string='Receipt Date', default=fields.Datetime.now, required=True)
    due_amount = fields.Float(string='Due Amount', required=True)
    payment_status = fields.Selection([('pending', 'Pending'), ('paid', 'Paid')], default='pending', required=True)
    paid_amount = fields.Float(string='Paid Amount', default=0.0, store=True)
    remaining_amount = fields.Float(string='Due Amount', store=True)
    amount_paying = fields.Float(string='Amount Paying', store=True)

    def _compute_remaining_amount(self):
        for record in self:
            if record.amount_paying > record.due_amount - record.paid_amount:
                raise UserError("The amount paying cannot exceed the remaining due amount.")
            record.remaining_amount = record.due_amount - record.paid_amount - record.amount_paying

    def action_process_receipt(self):
        for record in self:
            if record.amount_paying <= 0:
                raise UserError("Please enter a valid amount to pay.")
            if record.amount_paying > record.remaining_amount:
                raise UserError("You cannot pay more than the remaining due amount.")

            record.paid_amount += record.amount_paying
            record.remaining_amount -= record.amount_paying
            record.amount_paying = 0.0  # Reset the amount paying

            if record.remaining_amount <= 0:
                record.payment_status = 'paid'
            else:
                record.payment_status = 'pending'
