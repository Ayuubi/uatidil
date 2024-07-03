from odoo import models, fields, api
from odoo.exceptions import ValidationError


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
    description = fields.Text(string='Description', tracking=True)
    item_type = fields.Selection(
        selection=ITEM_TYPE_SELECTION,
        string='Item Type',
        required=True,
        tracking=True
    )
    item_category_id = fields.Many2one(comodel_name='idil.item.category', string='Item Category', required=True,
                                       help='Select Item Category', tracking=True)
    unitmeasure_id = fields.Many2one(comodel_name='idil.unit.measure', string='Unit of Measure', required=True,
                                     help='Select Unit of Measure', tracking=True)
    quantity = fields.Float(string='Quantity', required=True, tracking=True)
    min = fields.Float(string='Min Order', required=True, tracking=True)
    cost_price = fields.Float(string='Price per Unit', required=True, tracking=True)
    allergens = fields.Char(string='Allergens/Ingredients', tracking=True)
    image = fields.Binary(string=" Image")
    purchase_date = fields.Date(string='Purchase Date', required=True, tracking=True)
    expiration_date = fields.Date(string='Expiration Date', required=True, tracking=True)
    order_information = fields.Char(string='Order Information', tracking=True)
    bar_code = fields.Char(string='Bar Code', tracking=True)
    purchase_account_id = fields.Many2one(
        'idil.chart.account',
        string='Purchase Account',
        help='Account to report purchases of this item',
        required=True,
        tracking=True,
        domain="[('code', 'like', '5')]"  # Domain to filter accounts starting with '5'
    )

    sales_account_id = fields.Many2one(
        'idil.chart.account',
        string='Sales Account',
        help='Account to report sales of this item',
        required=True,
        tracking=True,
        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '4'
    )

    asset_account_id = fields.Many2one(
        'idil.chart.account',
        string='Asset Account',
        help='Account to report Asset of this item',
        required=True,
        tracking=True,
        domain="[('code', 'like', '1')]"  # Domain to filter accounts starting with '1'
    )

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
