from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class AccountHeader(models.Model):
    _name = 'idil.chart.account.header'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Chart of Accounts Header'

    code = fields.Char(string='Header Code', required=True)
    name = fields.Char(string='Header Name', required=True)

    sub_header_ids = fields.One2many('idil.chart.account.subheader', 'header_id', string='Sub Headers')


class AccountSubHeader(models.Model):
    _name = 'idil.chart.account.subheader'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Chart of Accounts Sub Header'

    sub_header_code = fields.Char(string='Sub Header Code', required=True)
    name = fields.Char(string='Sub Header Name', required=True)
    header_id = fields.Many2one('idil.chart.account.header', string='Header')
    account_ids = fields.One2many('idil.chart.account', 'subheader_id', string='Accounts')

    @api.constrains('sub_header_code')
    def _check_subheader_code_length(self):
        for subheader in self:
            if len(subheader.sub_header_code) != 6:
                raise ValidationError("Sub Header Code must be 6 characters long.")

    @api.constrains('sub_header_code', 'header_id')
    def _check_subheader_assignment(self):
        for subheader in self:
            header_code = subheader.header_id.code[:3]
            subheader_code = subheader.sub_header_code[:3]
            if not subheader_code.startswith(header_code):
                raise ValidationError("The first three digits of Sub Header Code must match the Header Code.")


class Account(models.Model):
    _name = 'idil.chart.account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Chart of Accounts'

    SIGN_SELECTION = [
        ('Dr', 'Dr'),
        ('Cr', 'Cr'),

    ]

    FINANCIAL_REPORTING_SELECTION = [
        ('BS', 'Balance Sheet'),
        ('PL', 'Profit and Loss'),
    ]
    account_type = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank'),
        ('payable', 'Account Payable'),
        ('receivable', 'Account Receivable'),
        ('COGS', 'COGS'),
    ]

    code = fields.Char(string='Account Code', required=True, tracking=True)
    name = fields.Char(string='Account Name', required=True, tracking=True)
    sign = fields.Selection(
        SIGN_SELECTION,
        string='Account Sign',
        compute='_compute_account_sign',
        store=True,
        tracking=True)
    FinancialReporting = fields.Selection(
        FINANCIAL_REPORTING_SELECTION,
        string='Financial Reporting',
        compute='_compute_financial_reporting',
        store=True,
        tracking=True
    )
    account_type = fields.Selection(
        account_type,
        string='Account Type',
        store=True,
        tracking=True
    )
    subheader_id = fields.Many2one('idil.chart.account.subheader', string='Sub Header', required=True, tracking=True)

    subheader_code = fields.Char(related='subheader_id.sub_header_code', string='Sub Header Code', readonly=True)
    subheader_name = fields.Char(related='subheader_id.name', string='Sub Header Name', readonly=True)
    header_code = fields.Char(related='subheader_id.header_id.code', string='Header Code', readonly=True)

    header_name = fields.Char(related='subheader_id.header_id.name', string='Header Name', readonly=True, store=True)

    @api.depends('code')
    def _compute_account_sign(self):
        for account in self:
            if account.code:
                first_digit = account.code[0]
                # Determine sign based on the first digit of the account code
                if first_digit in ['1', '5']:  # Assuming 1 and 5 represent Dr, adjust as needed
                    account.sign = 'Dr'
                elif first_digit in ['2', '3', '4']:
                    account.sign = 'Cr'
                else:
                    account.sign = False
            else:
                account.sign = False

    @api.depends('code')
    def _compute_financial_reporting(self):
        for account in self:
            if account.code:
                first_digit = account.code[0]
                # Determine financial reporting based on the first digit of the account code
                if first_digit in ['1', '2', '3']:  # Assuming 1, 2, 3 represent BS, adjust as needed
                    account.FinancialReporting = 'BS'
                elif first_digit in ['4', '5']:  # Assuming 4, 5 represent PL, adjust as needed
                    account.FinancialReporting = 'PL'
                else:
                    account.FinancialReporting = False
            else:
                account.FinancialReporting = False

    # class AccountBalanceReport(models.TransientModel):
    #     _name = 'idil.account.balance.report'
    #     _description = 'Account Balance Report'
    #
    #     type = fields.Char(string="Type")
    #     subtype = fields.Char(string="subtype")
    #     account_name = fields.Char(string="Account Name")
    #     account_code = fields.Char(string="Account Code")
    #     balance = fields.Float(string="Balance")
    #
    #     @api.model
    #     def generate_account_balances_report(self):
    #         # Assuming _get_account_balances() prepares the data correctly,
    #         # but instead of returning it, we'll use it to display in a view
    #
    #         # First, ensure any existing records are cleared to avoid stale data
    #         self.search([]).unlink()
    #
    #         # Now, generate new records based on current account balances
    #         account_balances = self._get_account_balances()
    #         for balance in account_balances:
    #             self.create({
    #                 'type': balance['type'],
    #                 'subtype': balance['subtype'],
    #                 'account_name': balance['account_name'],
    #                 'account_code': balance['account_code'],
    #                 'balance': balance['balance'],
    #             })
    #
    #         # Return an action to open the view with the newly created records
    #         return {
    #             'type': 'ir.actions.act_window',
    #             'name': 'Account Balances',
    #             'view_mode': 'tree',
    #             'res_model': 'idil.account.balance.report',
    #             'domain': [('balance', '<>', 0)],  # Add this line for the domain
    #             'context': {'group_by': ['type', 'subtype']},
    #             'target': 'new',
    #         }
    #
    #     def _get_account_balances(self):
    #         account_balances = []
    #         accounts = self.env['idil.chart.account'].search([])
    #
    #         for account in accounts:
    #             debit = sum(self.env['idil.transaction_bookingline'].search(
    #                 [('account_number', '=', account.code), ('transaction_type', '=', 'dr')]).mapped('dr_amount'))
    #             credit = sum(self.env['idil.transaction_bookingline'].search(
    #                 [('account_number', '=', account.code), ('transaction_type', '=', 'cr')]).mapped('cr_amount'))
    #
    #             balance = debit - credit
    #             account_balances.append({
    #                 'type': account.header_name,
    #                 'subtype': account.subheader_name,
    #                 'account_name': account.name,
    #                 'account_code': account.code,
    #                 'balance': balance,
    #             })
    #         return account_balances

    def calculate_balance(self):
        self.ensure_one()  # Ensure this method is called on a single record
        account_number = self.code  # Assuming this model has an account_number field

        # Fetching all transaction booking lines related to this account
        booking_lines = self.env['idil.transaction_bookingline'].search([('account_number', '=', account_number)])

        # Calculating the balance
        debit_total = sum(line.dr_amount for line in booking_lines if line.transaction_type == 'dr')
        credit_total = sum(line.cr_amount for line in booking_lines if line.transaction_type == 'cr')

        # The balance is the total of debits minus the total of credits
        balance = debit_total - credit_total
        return balance


class AccountBalanceReport(models.TransientModel):
    _name = 'idil.account.balance.report'
    _description = 'Account Balance Report'

    type = fields.Char(string="Type")
    subtype = fields.Char(string="subtype")
    account_name = fields.Char(string="Account Name")
    # account_code = fields.Char(string="Account Code")
    account_id = fields.Many2one('idil.chart.account', string="Account", store=True)
    balance = fields.Float(compute='_compute_balance', store=True)

    @api.depends('account_id')
    def _compute_balance(self):
        for report in self:
            # Initialize balance to 0 for each report entry
            report.balance = 0
            # Find transactions related to this account_code
            transactions = self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', report.account_id.id)])
            debit = sum(transactions.filtered(lambda r: r.transaction_type == 'dr').mapped('dr_amount'))
            credit = sum(transactions.filtered(lambda r: r.transaction_type == 'cr').mapped('cr_amount'))
            # Calculate balance
            report.balance = abs(debit - credit)

    @api.model
    def generate_account_balances_report(self):
        self.search([]).unlink()  # Clear existing records to avoid stale data

        account_balances = self._get_account_balances()
        for balance in account_balances:
            self.create({
                'type': balance['type'],
                'subtype': balance['subtype'],
                'account_name': balance['account_name'],
                'account_id': balance['account_id'],

            })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Account Balances',
            'view_mode': 'tree',
            'res_model': 'idil.account.balance.report',
            'domain': [('balance', '<>', 0)],  # Ensures only accounts with non-zero balances are shown
            'context': {'group_by': ['type', 'subtype']},
            'target': 'new',
        }

    def _get_account_balances(self):
        account_balances = []
        accounts = self.env['idil.chart.account'].search([])

        for account in accounts:
            account_balances.append({
                'type': account.header_name,
                'subtype': account.subheader_name,
                'account_name': account.name,
                'account_id': account.id,
            })
        return account_balances
