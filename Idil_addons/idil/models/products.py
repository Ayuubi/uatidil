# # models/product.py
# from odoo import models, fields, api
# from odoo.exceptions import ValidationError
#
#
# class Product(models.Model):
#     _name = 'my_product.product'
#     _description = 'Product'
#
#     name = fields.Char(string='Product Name', required=True)
#     internal_reference = fields.Char(string='Internal Reference', required=True)
#     stock_quantity = fields.Float(string='Stock Quantity', default=0.0)
#     category_id = fields.Many2one('idil.item.category', string='Product Category')
#     type = fields.Selection([
#         ('stockable', 'Stockable Product'),
#         ('consumable', 'Consumable'),
#         ('service', 'Service')],
#         string='Product Type', default='stockable', required=True)
#     sale_price = fields.Float(string='Sales Price', required=True)
#
#     # bom_id = fields.Many2one('idil.bom', string='BOM', help='Select BOM for costing')
#
#     cost = fields.Float(string='Cost', compute='_compute_product_cost', store=True)
#     sales_description = fields.Text(string='Sales Description')
#     purchase_description = fields.Text(string='Purchase Description')
#     uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')
#     taxes_id = fields.Many2one(
#         'idil.chart.account',
#         string='taxes Account',
#         help='Account to report Sales Taxes',
#         required=True,
#
#         domain="[('code', 'like', '5')]"  # Domain to filter accounts starting with '5'
#     )
#     income_account_id = fields.Many2one(
#         'idil.chart.account',
#         string='Income Account',
#         help='Account to report Sales Income',
#         required=True,
#
#         domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '5'
#     )
#
#     bom_id = fields.Many2one('idil.bom', string='BOM', help='Select BOM for costing',
#                              attrs={'invisible': [('costing_method', '=', 'fixedprice')]})
#     available_in_pos = fields.Boolean(string='Available in POS', default=True)
#     image_1920 = fields.Binary(string='Image')  # Assuming you use Odoo's standard image field
#
#     @api.depends('bom_id', 'bom_id.total_cost')
#     def _compute_product_cost(self):
#         for product in self:
#             if product.bom_id and product.bom_id.total_cost:
#                 product.cost = product.bom_id.total_cost
#             else:
#                 # If no BOM or total_cost, set the product cost to 0
#                 product.cost = 0.0

from odoo import models, fields, api


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
    cost = fields.Float(string='Cost', compute='_compute_product_cost', store=True)
    sales_description = fields.Text(string='Sales Description')
    purchase_description = fields.Text(string='Purchase Description')
    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')
    taxes_id = fields.Many2one(
        'idil.chart.account',
        string='Taxes Account',
        help='Account to report Sales Taxes',
        required=True,
        domain="[('code', 'like', '5')]"  # Domain to filter accounts starting with '5'
    )
    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Sales Income',
        required=True,
        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '4'
    )
    bom_id = fields.Many2one('idil.bom', string='BOM', help='Select BOM for costing')
    available_in_pos = fields.Boolean(string='Available in POS', default=True)
    image_1920 = fields.Binary(string='Image')  # Assuming you use Odoo's standard image field

    @api.depends('bom_id', 'bom_id.total_cost')
    def _compute_product_cost(self):
        for product in self:
            if product.bom_id and product.bom_id.total_cost:
                product.cost = product.bom_id.total_cost
            else:
                product.cost = 0.0

    @api.model
    def create(self, vals):
        res = super(Product, self).create(vals)
        res._sync_with_odoo_product()
        return res

    def write(self, vals):
        res = super(Product, self).write(vals)
        self._sync_with_odoo_product()
        return res

    def _sync_with_odoo_product(self):
        ProductProduct = self.env['product.product']
        type_mapping = {
            'stockable': 'product',
            'consumable': 'consu',
            'service': 'service'
        }
        for product in self:
            odoo_product = ProductProduct.search([('default_code', '=', product.internal_reference)], limit=1)
            if not odoo_product:
                odoo_product = ProductProduct.create({
                    'name': product.name,
                    'default_code': product.internal_reference,
                    'type': type_mapping[product.type],
                    'list_price': product.sale_price,
                    'standard_price': product.cost,
                    'categ_id': product.category_id.id if product.category_id else False,
                    'uom_id': product.uom_id.id if product.uom_id else False,
                    'available_in_pos': product.available_in_pos,
                    'image_1920': product.image_1920,
                })
            else:
                odoo_product.write({
                    'name': product.name,
                    'default_code': product.internal_reference,
                    'type': type_mapping[product.type],
                    'list_price': product.sale_price,
                    'standard_price': product.cost,
                    'categ_id': product.category_id.id if product.category_id else False,
                    'uom_id': product.uom_id.id if product.uom_id else False,
                    'available_in_pos': product.available_in_pos,
                    'image_1920': product.image_1920,
                })
