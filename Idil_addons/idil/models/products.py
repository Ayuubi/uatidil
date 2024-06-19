# models/product.py
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Product(models.Model):
    _name = 'my_product.product'
    _description = 'Product'

    name = fields.Char(string='Product Name', required=True)
    internal_reference = fields.Char(string='Internal Reference', required=True)
    stock_quantity = fields.Float(string='Stock Quantity', default=0.0)
    category_id = fields.Many2one('idil.item.category', string='Product Category')
    type = fields.Selection([
        ('stockable', 'Stockable Product'),
        ('consumable', 'Consumable'),
        ('service', 'Service')],
        string='Product Type', default='stockable', required=True)
    sale_price = fields.Float(string='Sales Price', required=True)

    # bom_id = fields.Many2one('idil.bom', string='BOM', help='Select BOM for costing')

    cost = fields.Float(string='Cost', compute='_compute_product_cost', store=True)
    sales_description = fields.Text(string='Sales Description')
    purchase_description = fields.Text(string='Purchase Description')
    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')
    taxes_id = fields.Many2one(
        'idil.chart.account',
        string='taxes Account',
        help='Account to report Sales Taxes',
        required=True,

        domain="[('code', 'like', '5')]"  # Domain to filter accounts starting with '5'
    )
    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Sales Income',
        required=True,

        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '5'
    )

    bom_id = fields.Many2one('idil.bom', string='BOM', help='Select BOM for costing',
                             attrs={'invisible': [('costing_method', '=', 'fixedprice')]})
    available_in_pos = fields.Boolean(string='Available in POS', default=True)

    @api.depends('bom_id', 'bom_id.total_cost')
    def _compute_product_cost(self):
        for product in self:
            if product.bom_id and product.bom_id.total_cost:
                product.cost = product.bom_id.total_cost
            else:
                # If no BOM or total_cost, set the product cost to 0
                product.cost = 0.0
