from datetime import datetime

from odoo import models, fields, api, exceptions
from odoo.exceptions import UserError, ValidationError
import re
import logging

_logger = logging.getLogger(__name__)


class TransactionBooking(models.Model):
    _name = 'idil.transaction_booking'
    _description = 'Transaction Booking'

    # Primary Key Fields
    transaction_number = fields.Integer(string='Transaction Number')
    reffno = fields.Char(string='Reference Number')  # Consider renaming for clarity
    journal_entry_id = fields.Many2one('idil.journal.entry', string='Journal Entry')

    vendor_id = fields.Many2one('idil.vendor.registration', string='Vendor')
    vendor_phone = fields.Char(related='vendor_id.phone', string='Vendor Phone', readonly=True)
    vendor_email = fields.Char(related='vendor_id.email', string='Vendor Email', readonly=True)

    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Sales Person')
    # Add a field to link to the SaleOrder. This assumes you have a unique identifier (like an ID) for SaleOrder.
    sale_order_id = fields.Many2one('idil.sale.order', string='Linked Sale Order', ondelete='cascade')

    order_number = fields.Char(string='Order Number')
    Sales_order_number = fields.Char(string='Sales Order Number')

    payment_method = fields.Selection(
        [('cash', 'Cash'), ('ap', 'A/P'), ('bank_transfer', 'Bank Transfer'), ('other', 'Other'),
         ('internal', 'Internal')],
        string='Payment Method'
    )

    pos_payment_method = fields.Many2one('pos.payment.method', string='POS Payment Method')

    payment_status = fields.Selection(
        [('pending', 'Pending'), ('paid', 'Paid'), ('partial_paid', 'Partial Paid')],
        string='Payment Status',
        help='Description or additional information about the payment status.'
    )
    trx_date = fields.Date(string='Transaction Date', default=lambda self: fields.Date.today())
    # amount = fields.Float(string='Amount')
    trx_source_id = fields.Many2one(
        'idil.transaction.source',
        string='Transaction Source',
        help="Select the transaction source."
    )
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True)
    amount_paid = fields.Float(string='Amount Paid')
    remaining_amount = fields.Float(string='Remaining Amount', store=True)

    debit_total = fields.Float(string='Total Debit', compute='_compute_debit_credit_total', store=True)
    credit_total = fields.Float(string='Total Credit', compute='_compute_debit_credit_total', store=True)

    booking_lines = fields.One2many(
        'idil.transaction_bookingline', 'transaction_booking_id', string='Transaction Lines'
    )

    # Add a Many2one field to select a cash account
    cash_account_id = fields.Many2one(
        'idil.chart.account',
        string='Cash Account',
        domain=[('account_type', '=', 'cash')],
        help="Select the cash account for transactions."
    )
    vendor_transactions = fields.One2many(
        'idil.vendor_transaction', 'transaction_booking_id', string='Vendor Transactions', ondelete='cascade'
    )

    # Add a Many2one field to link to PurchaseOrder
    purchase_order_id = fields.Many2one('idil.purchase_order', string='Linked Purchase Order', ondelete='cascade')

    @api.constrains('amount_paid')
    def _check_amount_paid(self):
        if self.env.context.get('skip_validations'):
            return
        for record in self:
            if record.amount_paid > record.amount:
                raise ValidationError(
                    "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
                        record.amount, record.amount_paid))

    @api.onchange('amount_paid')
    def _onchange_amount_paid(self):
        if self.env.context.get('skip_validations'):
            return
        if self.amount_paid > self.amount:
            raise ValidationError(
                "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
                    self.amount, self.amount_paid))

    def action_pay(self):
        for record in self:
            if not record.cash_account_id:
                raise ValidationError("Select Cash account")
            if record.amount_paid > record.amount:
                raise ValidationError("The payment amount cannot exceed the current balance.")

            # Create two transaction booking lines or update
            cr_account = record.sales_person_id.account_receivable_id.id
            dr_account = record.cash_account_id.id
            if cr_account and dr_account:
                # Find existing transaction booking lines

                existing_lines = self.env['idil.transaction_bookingline'].search([
                    ('transaction_booking_id', '=', record.id),
                    ('transaction_booking_id.payment_status', '!=', 'pending'),
                ])
                # Update existing lines or create them if they don't exist
                for line in existing_lines:
                    if line.description == "Receipt":
                        if line.transaction_type == 'cr':
                            line.cr_amount = record.amount_paid
                        elif line.transaction_type == 'dr':
                            line.dr_amount = record.amount_paid

                if not existing_lines:
                    # Create credit transaction booking line
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': record.id,
                        'description': 'Receipt',
                        'transaction_type': 'cr',
                        'cr_amount': record.amount_paid,
                        'dr_amount': 0,
                        'account_number': cr_account,
                    })

                    # Create debit transaction booking line
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': record.id,
                        'description': 'Receipt',
                        'transaction_type': 'dr',
                        'cr_amount': 0,
                        'dr_amount': record.amount_paid,
                        'account_number': dr_account,
                    })

                update_vals = {
                    'trx_source_id': 3,  # New trx_source_id value
                }

                # Update payment status based on remaining amount
                if record.remaining_amount == 0:
                    record.payment_status = 'paid'
                else:
                    record.payment_status = 'partial_paid'

                record.amount_paid = record.amount_paid
                record.remaining_amount = record.remaining_amount
                # Write the changes to the database
                record.write(update_vals)
            else:
                # Log an error or handle the case where accounts are not properly set
                _logger.error(f"Accounts not properly set for transaction booking {record.id}.")

    @api.depends('booking_lines.dr_amount', 'booking_lines.cr_amount')
    def _compute_debit_credit_total(self):
        for record in self:
            record.debit_total = sum(line.dr_amount for line in record.booking_lines)
            record.credit_total = sum(line.cr_amount for line in record.booking_lines)

    @api.model
    def create(self, vals):
        # vals['reffno'] = self._generate_booking_reference(vals)
        vals['transaction_number'] = self._get_next_transaction_number()

        transaction_record = super(TransactionBooking, self).create(vals)

        return transaction_record

    def _get_next_transaction_number(self):
        max_transaction_number = self.env['idil.transaction_booking'].search([], order='transaction_number desc',
                                                                             limit=1).transaction_number or 0
        return max_transaction_number + 1

    def action_add_default_lines(self):
        for record in self:
            # Add a debit line
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': record.id,
                'transaction_type': 'dr',
                'dr_amount': 0.0,  # Default amount; adjust as necessary
                'cr_amount': 0.0,  # Ensured to be zero for debit line
                'description': 'Default debit line',
            })
            # Add a credit line
            self.env['idil.transaction_bookingline'].create({
                'transaction_booking_id': record.id,
                'transaction_type': 'cr',
                'dr_amount': 0.0,  # Ensured to be zero for credit line
                'cr_amount': 0.0,  # Default amount; adjust as necessary
                'description': 'Default credit line',
            })

    def update_related_booking_lines(self):
        for line in self.booking_lines:
            if line.transaction_type == 'dr':
                line.dr_amount = self.amount  # Update dr_amount to total sale order amount for debit lines
                line.cr_amount = 0
            elif line.transaction_type == 'cr':
                line.cr_amount = self.amount  # Update cr_amount to total sale order amount for credit lines
                line.dr_amount = 0


class TransactionBookingline(models.Model):
    _name = 'idil.transaction_bookingline'
    _description = 'Transaction Booking Line'

    # Secondary Key Fields
    transaction_booking_id = fields.Many2one(
        'idil.transaction_booking', string='Transaction Booking', ondelete='cascade'
    )

    # order_line = fields.Char(string='Order Line')
    order_line = fields.Integer(string='Order Line')

    description = fields.Char(string='Description')
    item_id = fields.Many2one('idil.item', string='Item')
    product_id = fields.Many2one('my_product.product', string='Product')

    account_number = fields.Many2one(
        'idil.chart.account', string='Account Number', required=True
    )

    transaction_type = fields.Selection(
        [('dr', 'Debit'), ('cr', 'Credit')], string='Transaction Type', required=True
    )
    dr_amount = fields.Float(string='Debit Amount')
    cr_amount = fields.Float(string='Credit Amount')
    transaction_date = fields.Date(string='Transaction Date', default=lambda self: fields.Date.today())
    vendor_payment_id = fields.Many2one('idil.vendor_payment', string='Vendor Payment', ondelete='cascade')
    currency_id = fields.Many2one('res.currency', string='Currency', related='account_number.currency_id', store=True,
                                  readonly=True)

    # @api.model
    # def compute_trial_balance(self):
    #     self.env.cr.execute("""
    #             SELECT
    #                 tb.account_number,
    #                 ca.currency_id,
    #                 SUM(tb.dr_amount) AS dr_total,
    #                 SUM(tb.cr_amount) AS cr_total
    #             FROM
    #                 idil_transaction_bookingline tb
    #             JOIN idil_chart_account ca ON tb.account_number = ca.id
    #             JOIN idil_chart_account_subheader cb ON ca.subheader_id = cb.id
    #             JOIN idil_chart_account_header ch ON cb.header_id = ch.id
    #             GROUP BY
    #                 tb.account_number, ca.currency_id, ch.code
    #             HAVING
    #                 SUM(tb.dr_amount) - SUM(tb.cr_amount) <> 0
    #             ORDER BY
    #                 ch.code
    #         """)
    #     result = self.env.cr.dictfetchall()
    #
    #     total_dr_balance = 0
    #     total_cr_balance = 0
    #
    #     self.env['idil.trial.balance'].search([]).unlink()
    #
    #     for line in result:
    #         account = self.env['idil.chart.account'].browse(line['account_number'])
    #         if account.sign == 'Dr':
    #             dr_balance = line['dr_total'] - line['cr_total']
    #             cr_balance = 0
    #             total_dr_balance += dr_balance
    #         else:
    #             dr_balance = 0
    #             cr_balance = line['cr_total'] - line['dr_total']
    #             total_cr_balance += cr_balance
    #
    #         currency_id = line['currency_id']
    #
    #         self.env['idil.trial.balance'].create({
    #             'account_number': account.id,
    #             'header_name': account.header_name,
    #             'currency_id': currency_id,
    #             'dr_balance': max(dr_balance, 0),
    #             'cr_balance': max(cr_balance, 0),
    #         })
    #
    #         # Create a record to store the grand totals with a label
    #         self.env['idil.trial.balance'].create({
    #             'account_number': None,
    #             'currency_id': currency_id,
    #             'dr_balance': total_dr_balance,
    #             'cr_balance': total_cr_balance,
    #             'label': 'Grand Total'
    #         })
    #
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'name': 'Trial Balance',
    #         'view_mode': 'tree',
    #         'res_model': 'idil.trial.balance',
    #         'target': 'new',
    #     }

    @api.model
    def compute_trial_balance(self, report_currency_id):
        self.env.cr.execute("""
                SELECT
                    tb.account_number,
                    ca.currency_id,
                    SUM(tb.dr_amount) AS dr_total,
                    SUM(tb.cr_amount) AS cr_total
                FROM
                    idil_transaction_bookingline tb
                JOIN idil_chart_account ca ON tb.account_number = ca.id
                JOIN idil_chart_account_subheader cb ON ca.subheader_id = cb.id
                JOIN idil_chart_account_header ch ON cb.header_id = ch.id
                WHERE
                    ca.currency_id = %s  -- Filter by selected report currency
                GROUP BY
                    tb.account_number, ca.currency_id, ch.code
                HAVING
                    SUM(tb.dr_amount) - SUM(tb.cr_amount) <> 0
                ORDER BY
                    ch.code
            """, (report_currency_id.id,))
        result = self.env.cr.dictfetchall()

        total_dr_balance = 0
        total_cr_balance = 0

        self.env['idil.trial.balance'].search([]).unlink()

        for line in result:
            account = self.env['idil.chart.account'].browse(line['account_number'])
            if account.sign == 'Dr':
                dr_balance = line['dr_total'] - line['cr_total']
                cr_balance = 0
                total_dr_balance += dr_balance
            else:
                dr_balance = 0
                cr_balance = line['cr_total'] - line['dr_total']
                total_cr_balance += cr_balance

            self.env['idil.trial.balance'].create({
                'account_number': account.id,
                'header_name': account.header_name,
                'currency_id': line['currency_id'],
                'dr_balance': max(dr_balance, 0),
                'cr_balance': max(cr_balance, 0),
            })

        if report_currency_id:
            self.env['idil.trial.balance'].create({
                'account_number': None,
                'currency_id': report_currency_id.id,
                'dr_balance': total_dr_balance,
                'cr_balance': total_cr_balance,
                'label': 'Grand Total'
            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Trial Balance',
            'view_mode': 'tree',
            'res_model': 'idil.trial.balance',
            'target': 'new',
        }
