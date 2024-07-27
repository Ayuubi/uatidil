from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


class item(models.Model):
    _name = 'idil.item'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Idil Purchased Items'

    ITEM_TYPE_SELECTION = [
        ('service', 'Service'),
        ('inventory', 'Inventory'),
        ('non_inventory', 'Non-Inventory'),
        ('discount', 'Discount'),
        ('payment', 'Payment'),
        ('tax', 'Tax'),
        ('mileage', 'Mileage'),
        # Add more QuickBooks item types as needed
    ]
    name = fields.Char(string='Item Name', required=True, tracking=True)
    active = fields.Boolean(string="Archive", default=True, tracking=True)

    description = fields.Text(string='Description', tracking=True)
    item_type = fields.Selection(
        selection=ITEM_TYPE_SELECTION,
        string='Item Type',
        required=True,
        tracking=True
    )
    quantity = fields.Float(string='Quantity', required=True, tracking=True, default=0.0)

    purchase_date = fields.Date(string='Purchase Date', required=True, tracking=True, default=fields.Date.today)
    expiration_date = fields.Date(string='Expiration Date', required=True, tracking=True)
    item_category_id = fields.Many2one(comodel_name='idil.item.category', string='Item Category', required=True,
                                       help='Select Item Category', tracking=True)
    unitmeasure_id = fields.Many2one(comodel_name='idil.unit.measure', string='Unit of Measure', required=True,
                                     help='Select Unit of Measure', tracking=True)
    min = fields.Float(string='Min Order', required=True, tracking=True)
    cost_price = fields.Float(string='Price per Unit', required=True, tracking=True)
    allergens = fields.Char(string='Allergens/Ingredients', tracking=True)
    image = fields.Binary(string=" Image")
    order_information = fields.Char(string='Order Information', tracking=True)
    bar_code = fields.Char(string='Bar Code', tracking=True)

    purchase_account_id = fields.Many2one(
        'idil.chart.account',
        string='Purchase Account',
        help='Account to report purchases of this item',
        required=True,
        tracking=True,
        domain="[('account_type', 'like', 'COGS'), ('currency_id.name', '=', 'USD')]"  # Corrected domain structure
    )
    sales_account_id = fields.Many2one(
        'idil.chart.account',
        string='Sales Account',
        help='Account to report sales of this item',
        required=True,
        tracking=True,
        domain="[('code', 'like', '4'), ('currency_id.name', '=', 'USD')]"
        # Domain to filter accounts starting with '4' and in USD
    )
    asset_account_id = fields.Many2one(
        'idil.chart.account',
        string='Asset Account',
        help='Account to report Asset of this item',
        required=True,
        tracking=True,
        domain="[('code', 'like', '1'), ('currency_id.name', '=', 'USD')]"
        # Domain to filter accounts starting with '1' and in USD
    )
    days_until_expiration = fields.Integer(string='Days Until Expiration', compute='_compute_days_until_expiration',
                                           store=True, readonly=True)

    @api.constrains('name')
    def _check_unique_name(self):
        for record in self:
            if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                raise ValidationError('Item name must be unique. The name "%s" is already in use.' % record.name)

    @api.depends('expiration_date')
    def _compute_days_until_expiration(self):
        for record in self:
            if record.expiration_date:
                delta = record.expiration_date - fields.Date.today()
                record.days_until_expiration = delta.days
            else:
                record.days_until_expiration = 0

    @api.constrains('purchase_date', 'expiration_date')
    def check_date_not_in_past(self):
        for record in self:
            today = fields.Date.today()
            if record.purchase_date < today or record.expiration_date < today:
                raise ValidationError("Both purchase and expiration dates must be today or in the future.")

    def adjust_stock(self, qty):
        """Safely adjust the stock quantity, preventing negative values."""
        for record in self:
            new_quantity = record.quantity - qty
            if new_quantity < 0:
                # Prevent adjustment to negative. Raise a ValidationError to inform the user.
                raise ValidationError(
                    f'Cannot reduce stock below zero for item {record.name}. Adjustment quantity: {qty}, Current stock: {record.quantity}')
            else:
                record.quantity = new_quantity

    @api.constrains('quantity', 'cost_price')
    def _check_positive_values(self):
        for record in self:
            if record.quantity < 0:
                raise ValidationError('Quantity must be a positive value.')
            if record.cost_price < 0:
                raise ValidationError('Cost price must be a positive value.')

    def check_reorder(self):
        """Send notifications for items that need reordering."""
        for record in self:
            if record.quantity < record.min:
                # Logic to send notification or create a reorder
                record.message_post(body=f'Item {record.name} needs reordering. Current stock: {record.quantity}')

    @api.model
    def create(self, vals):
        new_item = super(item, self).create(vals)

        # Get the transaction source for inventory opening balance
        inventory_opening_balance_source = self.env['idil.transaction.source'].search(
            [('name', '=', 'Inventory Opening Balance')], limit=1)
        if not inventory_opening_balance_source:
            raise ValidationError("Transaction source 'Inventory Opening Balance' not found. "
                                  "Please configure the transaction source correctly.")

        # Get the equity account ID dynamically
        equity_account = self.env['idil.chart.account'].search(
            [('account_type', '=', 'Owners Equity'), ('currency_id.name', '=', 'USD')], limit=1)

        if not equity_account:
            raise ValidationError("Equity account not found. Please configure the equity account correctly.")

        # Create the transaction booking for the opening balance
        transaction_booking = self.env['idil.transaction_booking'].create({
            'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction_booking'),
            'reffno': new_item.name,
            'trx_date': fields.Date.today(),
            'amount': new_item.quantity * new_item.cost_price,
            'amount_paid': new_item.quantity * new_item.cost_price,
            'remaining_amount': 0,
            'payment_status': 'paid',
            'payment_method': "other",
            'trx_source_id': inventory_opening_balance_source.id
        })

        # Create the transaction lines
        transaction_booking.booking_lines.create({
            'transaction_booking_id': transaction_booking.id,
            'description': 'Opening Balance for Item %s' % new_item.name,
            'item_id': new_item.id,
            'account_number': new_item.asset_account_id.id,
            'transaction_type': 'dr',
            'dr_amount': new_item.quantity * new_item.cost_price,
            'cr_amount': 0,
            'transaction_date': fields.Date.today()
        })

        transaction_booking.booking_lines.create({
            'transaction_booking_id': transaction_booking.id,
            'description': 'Opening Balance for Item %s' % new_item.name,
            'item_id': new_item.id,
            'account_number': equity_account.id,
            'transaction_type': 'cr',
            'cr_amount': new_item.quantity * new_item.cost_price,
            'dr_amount': 0,
            'transaction_date': fields.Date.today()
        })

        return new_item

    def write(self, vals):
        res = super(item, self).write(vals)
        if 'quantity' in vals:
            for record in self:
                new_amount = record.quantity * record.cost_price
                transaction_bookings = self.env['idil.transaction_booking'].search([('reffno', '=', record.name)])
                for booking in transaction_bookings:
                    booking.amount = new_amount
                    booking.amount_paid = new_amount
                    for line in booking.booking_lines:
                        if line.account_number.id == record.asset_account_id.id:
                            line.dr_amount = new_amount
                            line.cr_amount = 0
                        elif line.account_number.account_type == 'Owners Equity':
                            line.cr_amount = new_amount
                            line.dr_amount = 0
        return res
