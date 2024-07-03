from odoo import models, fields, api
import logging

from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class SalesPersonnel(models.Model):
    _name = 'idil.sales.sales_personnel'
    _description = 'Sales Personnel Information'

    name = fields.Char(string='Name', required=True)
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    active = fields.Boolean(string='Active', default=True)
    image = fields.Binary(string="Image")
    account_receivable_id = fields.Many2one(
        'idil.chart.account',
        string='Receivable Account',
        domain=[('account_type', '=', 'receivable')],
        help="Select the receivable account for transactions."
    )
    address = fields.Text(string='Address')
    balance = fields.Float(string="Balance", store=True)


class SalesPersonBalanceReport(models.TransientModel):
    _name = 'idil.sales.balance.report'
    _description = 'Sales Personnel Balance Report'

    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Sales Person')
    sales_person_name = fields.Char(string="Sales Person Name")
    sales_person_phone = fields.Char(string="Sales Person Phone number")
    account_id = fields.Many2one('idil.chart.account', string="Account", store=True)
    account_name = fields.Char(string="Account Name")
    account_code = fields.Char(string="Account Code")
    # balance = fields.Float(compute='_compute_sales_person_balance', store=True)
    balance = fields.Float(string="Balance", store=True)
    amount_paid = fields.Float(string='Amount Paid')
    remaining_amount = fields.Float(string='Remaining Amount', compute='_compute_remaining_amount', store=True)

    @api.model
    def generate_sales_person_balances_report(self):
        self.search([]).unlink()  # Clear existing records
        sales_person_balances = self._get_sales_person_balances()
        for balance in sales_person_balances:
            self.create({
                'sales_person_name': balance['sales_person_name'],
                'sales_person_phone': balance['sales_person_phone'],
                'account_name': balance['account_name'],
                'account_id': balance['account_id'],
                'account_code': balance['account_code'],
                'balance': balance['balance'],
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Sales Personnel Balances',
            'view_mode': 'tree',
            'res_model': 'idil.sales.balance.report',
            'domain': [('balance', '<>', 0)],
            'context': {'group_by': ['sales_person_name']},
            'target': 'new',
        }

    def _get_sales_person_balances(self):
        sales_person_balances = []
        sales_personnel = self.env['idil.sales.sales_personnel'].search([('active', '=', True)])
        for person in sales_personnel:
            # Initialize balance for each salesperson.
            booking_lines_balance = 0
            sales_orders = self.env['idil.sale.order'].search([('sales_person_id', '=', person.id)])
            for order in sales_orders:
                bookings = self.env['idil.transaction_booking'].search([('sale_order_id', '=', order.id)])
                for booking in bookings:
                    # Filter booking lines by account number equal to salesperson's receivable account.
                    booking_lines = self.env['idil.transaction_bookingline'].search([
                        ('transaction_booking_id', '=', booking.id),
                        ('account_number', '=', person.account_receivable_id.id)
                    ])
                    # Calculate debit and credit sums for filtered booking lines.
                    debit = sum(booking_lines.filtered(lambda r: r.transaction_type == 'dr').mapped('dr_amount'))
                    credit = sum(booking_lines.filtered(lambda r: r.transaction_type == 'cr').mapped('cr_amount'))
                    booking_lines_balance += debit - credit

            # Debugging: Log the calculated balance for each salesperson.
            _logger.debug(f"Salesperson: {person.name}, Balance: {booking_lines_balance}")

            sales_person_balances.append({
                'sales_person_id': person.id,
                'sales_person_name': person.name,
                'sales_person_phone': person.phone,
                'account_name': person.account_receivable_id.name if person.account_receivable_id else '',
                'account_id': person.account_receivable_id.id if person.account_receivable_id else False,
                'account_code': person.account_receivable_id.code if person.account_receivable_id else '',
                'balance': booking_lines_balance,
            })

        return sales_person_balances
