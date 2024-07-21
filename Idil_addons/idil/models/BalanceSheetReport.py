from odoo import models, fields, api


class BalanceSheetReport(models.TransientModel):
    _name = 'idil.balance.sheet.report'
    _description = 'Balance Sheet Report'

    type = fields.Char(string="Type")
    subtype = fields.Char(string="Subtype")
    account_name = fields.Char(string="Account Name")
    account_code = fields.Char(string="Account Code")
    balance = fields.Float(string="Balance")
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    category = fields.Selection([
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity')
    ], string='Category')

    def _get_account_balances(self):
        account_balances = []
        accounts = self.env['idil.chart.account'].search([])

        categories = {
            '1': 'asset',
            '2': 'liability',
            '3': 'equity',
        }

        totals = {
            'asset': 0,
            'liability': 0,
            'equity': 0,
        }

        for account in accounts:
            debit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', account.code), ('transaction_type', '=', 'dr')]).mapped('dr_amount'))
            credit = sum(self.env['idil.transaction_bookingline'].search(
                [('account_number', '=', account.code), ('transaction_type', '=', 'cr')]).mapped('cr_amount'))

            balance = debit - credit
            category = categories.get(account.code[0], 'unknown')

            if category in totals:
                totals[category] += balance

            account_balances.append({
                'type': account.header_name,
                'subtype': account.subheader_name,
                'account_name': account.name,
                'account_code': account.code,
                'balance': balance,
                'currency_id': account.currency_id.id,
                'category': category,
            })

        return account_balances

    def generate_balance_sheet_report(self):
        account_balances = self._get_account_balances()
        asset_accounts = [acc for acc in account_balances if acc['category'] == 'asset']
        liability_accounts = [acc for acc in account_balances if acc['category'] == 'liability']
        equity_accounts = [acc for acc in account_balances if acc['category'] == 'equity']

        asset_total = sum(acc['balance'] for acc in asset_accounts)
        liability_total = sum(acc['balance'] for acc in liability_accounts)
        equity_total = sum(acc['balance'] for acc in equity_accounts)

        report_data = {
            'asset_accounts': asset_accounts,
            'liability_accounts': liability_accounts,
            'equity_accounts': equity_accounts,
            'asset_total': asset_total,
            'liability_total': liability_total,
            'equity_total': equity_total,
        }

        return self.env.ref('idil.report_balance_sheet').report_action(self, data=report_data)
