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
    vendor_id = fields.Many2one('idil.vendor.registration', string='Vendor')
    vendor_phone = fields.Char(related='vendor_id.phone', string='Vendor Phone', readonly=True)
    vendor_email = fields.Char(related='vendor_id.email', string='Vendor Email', readonly=True)

    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Sales Person')
    # Add a field to link to the SaleOrder. This assumes you have a unique identifier (like an ID) for SaleOrder.
    sale_order_id = fields.Many2one('idil.sale.order', string='Linked Sale Order', ondelete='cascade')

    order_number = fields.Char(string='Order Number')
    Sales_order_number = fields.Char(string='Sales Order Number')

    payment_method = fields.Selection(
        [('cash', 'Cash'), ('ap', 'A/P'), ('bank_transfer', 'Bank Transfer'), ('other', 'other')],
        string='Payment Method', required=True
    )

    pos_payment_method = fields.Many2one('pos.payment.method', string='POS Payment Method', required=True)

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
    remaining_amount = fields.Float(string='Remaining Amount', compute='_compute_remaining_amount', store=True)

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

    # Code for sales receipt ------------------------------------
    @api.depends('amount', 'amount_paid')
    def _compute_remaining_amount(self):
        for record in self:
            record.remaining_amount = record.amount - record.amount_paid

    # Code for sales receipt
    # @api.constrains('amount_paid')
    # def _check_amount_paid(self):
    #     for record in self:
    #         if record.amount_paid > record.amount:
    #             raise ValidationError(
    #                 "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
    #                     self.amount, self.amount_paid))

    @api.constrains('amount_paid')
    def _check_amount_paid(self):
        if self.env.context.get('skip_validations'):
            return
        for record in self:
            if record.amount_paid > record.amount:
                raise ValidationError(
                    "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
                        record.amount, record.amount_paid))

    # Code for sales receipt
    # @api.onchange('amount_paid')
    # def _onchange_amount_paid(self):
    #     if self.amount_paid > self.amount:
    #         raise ValidationError(
    #             "The paid amount cannot be greater than the balance.\nBalance: %s\nAmount Needed to Pay: %s" % (
    #                 self.amount, self.amount_paid))

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

    # def write(self, values):
    #     # This is not avoid form edit button when sales receipt only if make error to review sales receipt again
    #     raise exceptions.UserError('Editing fields using this button is not allowed, use PAY button.')

    # ----------------------------------------------------------------------------------------------------
    def _calculate_account_balance(self, account_id, account_type):
        transactions = self.env['idil.transaction_bookingline'].search([('account_number', '=', account_id)])
        total_debit = sum(transaction.dr_amount for transaction in transactions if transaction.transaction_type == 'dr')
        total_credit = sum(
            transaction.cr_amount for transaction in transactions if transaction.transaction_type == 'cr')

        if account_type in ['Asset', 'Expense']:
            return total_debit - total_credit
        else:  # Liability, Equity, Income
            return total_credit - total_debit

    @api.model
    def _generate_booking_reference(self, vals):
        vendor_id = 'BO'  # Assuming this is static for demonstration purposes
        if vendor_id:
            vendor_name = f'ReffNo#{self._get_next_transaction_number()}'
            date_str = '/' + datetime.now().strftime('%d%m%Y')
            day_night = '/DAY/' if datetime.now().hour < 12 else '/NIGHT/'
            sequence = self.env['ir.sequence'].next_by_code('idil.transaction_booking.sequence')

            # No need to slice the sequence, let's use it as is
            # Ensure sequence is always provided, even as a fallback
            if not sequence:
                sequence = '000'

            booking_ref = f"{vendor_name}{date_str}{day_night}{sequence}"
        else:
            # Fallback if no vendor ID is provided, just an example
            sequence = self.env['ir.sequence'].next_by_code('idil.transaction_booking.sequence')
            booking_ref = sequence if sequence else '000'

        return booking_ref

    @api.constrains('booking_lines')
    def validate_transaction_balances(self):
        total_debit = 0.0
        total_credit = 0.0
        for record in self:
            if not record.booking_lines:
                raise ValidationError("Transaction must have at least one booking line.")

            for line in record.booking_lines:
                account_id = line.account_number.id
                account_type = self._get_account_type_from_number(account_id)
                transaction_type = line.transaction_type
                transaction_amount = line.dr_amount if transaction_type == 'dr' else line.cr_amount

                # Calculate the current account balance before this transaction
                current_balance = self._calculate_account_balance(account_id, account_type)

                # Check if the current transaction will decrease the account balance
                # For Asset and Expense accounts, a credit transaction decreases the balance
                # For Liability, Equity, and Income accounts, a debit transaction decreases the balance
                if (account_type in ['Asset',
                                     'Expense'] and transaction_type == 'cr' and current_balance < transaction_amount) or \
                        (account_type in ['Liability', 'Equity',
                                          'Income'] and transaction_type == 'dr' and current_balance < transaction_amount):
                    raise ValidationError(
                        f"Account {account_id} does not have enough balance for this transaction. Current balance is {current_balance}, transaction amount is {transaction_amount}.")

                # Accumulate total debits and credits
                if line.transaction_type == 'dr':
                    total_debit += line.dr_amount
                elif line.transaction_type == 'cr':
                    total_credit += line.cr_amount

            # Ensure the total of debit amounts equals the total of credit amounts
            if total_debit != total_credit:
                raise ValidationError("The total of debit amounts must equal the total of credit amounts.")

    def _get_account_type_from_number(self, account_id):
        # Placeholder for the actual implementation of fetching account type
        account = self.env['account.account'].browse(account_id)
        if not account:
            return 'unknown'

        account_number = account.code
        if not account_number:
            return 'unknown'

        first_digit = account_number[0]
        account_type_mapping = {
            '1': 'Asset',
            '2': 'Liability',
            '3': 'Equity',
            '4': 'Income',
            '5': 'Expense',
        }
        return account_type_mapping.get(first_digit, 'unknown')

    @api.model
    def create(self, vals):
        vals['reffno'] = self._generate_booking_reference(vals)
        vals['transaction_number'] = self._get_next_transaction_number()

        # Only set a default trx_source_id if it's not provided in vals
        if 'trx_source_id' not in vals:
            default_trx_source_id = self.env['idil.transaction.source'].search([('name', '=', 'manual_booking')],
                                                                               limit=1).id
            vals['trx_source_id'] = default_trx_source_id

        transaction_record = super(TransactionBooking, self).create(vals)

        # Assume `vals` includes line data that has account and type information
        if 'line_data' in vals:
            for line in vals['line_data']:
                self._create_transaction_line(transaction_record.id, line)

        return transaction_record

    def _get_next_transaction_number(self):
        max_transaction_number = self.env['idil.transaction_booking'].search([], order='transaction_number desc',
                                                                             limit=1).transaction_number or 0
        return max_transaction_number + 1

    def _create_transaction_line(self, transaction_id, line):
        account_code = line.get('account_code')
        transaction_type = line.get('transaction_type')
        account = self.env['idil.chart.account'].search([('code', '=', account_code)], limit=1)
        if not account:
            _logger.error(f"Account with code {account_code} not found.")
            return

        line_vals = {

            'amount': line.get('amount', 0.0),

            'order_line': 0,
            'item_id': 0,
            'account_number': account,
            'transaction_type': transaction_type,
            'dr_amount': self.amount if transaction_type == 'dr' else 0,
            'cr_amount': self.amount if transaction_type == 'cr' else 0,
            'transaction_date': fields.Date.today(),
            'transaction_booking_id': transaction_id,
        }
        try:
            self.env['idil.transaction_bookingline'].create(line_vals)
            _logger.info(f"Creating transaction line with values: {line_vals}")
        except Exception as e:
            _logger.error(f"Error creating transaction line: {e}")

    def set_payment_status_paid(self):
        for record in self:
            record['trx_source_id'] = self.env['idil.transaction.source'].search([('name', '=', 'pay_vendor')],
                                                                                 limit=1).id
            if record.payment_status == 'pending':
                if not record.cash_account_id:
                    raise UserError('Please select a cash account before setting the payment status to paid.')

                transactions = self.env['idil.transaction_bookingline'].search([
                    ('account_number', '=', record.cash_account_id.id)
                ])

                total_debit = sum(transactions.mapped('dr_amount'))
                total_credit = sum(transactions.mapped('cr_amount'))
                current_balance = total_debit - total_credit

                if current_balance < record.amount:
                    raise UserError(
                        'The selected cash account does not have enough balance.')

                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': record.id,
                    'account_number': record.cash_account_id.id,
                    'transaction_type': 'cr',
                    'cr_amount': record.amount,
                    'transaction_date': fields.Date.today(),
                })

                # Fetch the vendor's payable account
                vendor = self.env['idil.vendor.registration'].browse(record.vendor_id.id)
                if not vendor.account_payable_id:
                    raise UserError('Vendor payable account not found.')

                # Create transaction booking line for the vendor payable (Debit)
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': record.id,
                    'account_number': vendor.account_payable_id.id,
                    'transaction_type': 'dr',
                    'dr_amount': record.amount,
                    'transaction_date': fields.Date.today(),
                })

                record.payment_status = 'paid'
            else:
                raise UserError('The payment status is already paid or not applicable.')

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

    @api.depends('booking_lines.dr_amount', 'booking_lines.cr_amount', 'trx_source_id')
    def _compute_amount(self):
        for record in self:
            if record.trx_source_id.name != 'pay_vendor' and record.trx_source_id.name != 'sales_order':
                total_amount = sum(line.dr_amount for line in record.booking_lines)
                record.amount = total_amount

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
