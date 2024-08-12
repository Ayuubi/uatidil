from odoo import models, fields, api


class Product(models.Model):
    _name = 'my_product.product'
    _description = 'Product'

    name = fields.Char(string='Product Name', required=True)
    internal_reference = fields.Char(string='Internal Reference', required=True)
    stock_quantity = fields.Float(string='Stock Quantity', default=0.0)
    category_id = fields.Many2one('product.category', string='Product Category')
    # New field for POS categories
    available_in_pos = fields.Boolean(string='Available in POS', default=True)

    pos_categ_ids = fields.Many2many('pos.category', string='POS Categories',
                                     )

    detailed_type = fields.Selection([
        ('consu', 'Consumable'),
        ('service', 'Service')
    ], string='Product Type', default='consu', required=True,
        help='A storable product is a product for which you manage stock. The Inventory app has to be installed.\n'
             'A consumable product is a product for which stock is not managed.\n'
             'A service is a non-material product you provide.')

    sale_price = fields.Float(string='Sales Price', required=True)
    cost = fields.Float(string='Cost', compute='_compute_product_cost', store=True)
    sales_description = fields.Text(string='Sales Description')
    purchase_description = fields.Text(string='Purchase Description')
    uom_id = fields.Many2one('idil.unit.measure', string='Unit of Measure')

    taxes_id = fields.Many2one(
        'idil.chart.account',
        string='Taxes Account',
        help='Account to report Sales Taxes',
        domain="[('code', 'like', '5')]"  # Domain to filter accounts starting with '5'
    )

    income_account_id = fields.Many2one(
        'idil.chart.account',
        string='Income Account',
        help='Account to report Sales Income',
        required=True,
        domain="[('code', 'like', '4')]"  # Domain to filter accounts starting with '4'
    )

    asset_currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                        default=lambda self: self.env.company.currency_id)

    asset_account_id = fields.Many2one(
        'idil.chart.account',
        string='Inventory Asset Account',
        help='Account to report Asset of this item',
        required=True,
        tracking=True,
        domain="[('code', 'like', '1'), ('currency_id', '=', asset_currency_id)]"
        # Domain to filter accounts starting with '1' and in USD
    )

    bom_id = fields.Many2one('idil.bom', string='BOM', help='Select BOM for costing')
    image_1920 = fields.Binary(string='Image')  # Assuming you use Odoo's standard image field

    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id)

    account_id = fields.Many2one('idil.chart.account', string='Commission Account',
                                 domain="[('account_type', 'like', 'commission'), ('code', 'like', '5%'), "
                                        "('currency_id', '=', currency_id)]"
                                 )

    is_commissionable = fields.Boolean(string='Commissionable', default=False)

    sales_currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                        default=lambda self: self.env.company.currency_id)
    sales_account_id = fields.Many2one('idil.chart.account', string='Sales Commission Account',
                                       domain="[('account_type', 'like', 'commission'), ('code', 'like', '5%'), "
                                              "('currency_id', '=', sales_currency_id)]"
                                       )
    is_sales_commissionable = fields.Boolean(string='Commissionable', default=False)
    commission = fields.Float(string='Commission Rate')

    is_quantity_discount = fields.Boolean(string='Quantity Discount', default=False)
    discount_currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                           default=lambda self: self.env.company.currency_id)
    discount = fields.Float(string='Discount Rate')
    sales_discount_id = fields.Many2one('idil.chart.account', string='Sales Discount Account',
                                        domain="[('account_type', 'like', 'discount'), ('code', 'like', '5%'), "
                                               "('currency_id', '=', discount_currency_id)]"
                                        )

    @api.onchange('asset_currency_id')
    def _onchange_asset_currency_id(self):
        """Updates the domain for account_id based on the selected currency."""
        for asset_account in self:
            if asset_account.asset_currency_id:
                asset_account.asset_account_id = False  # Clear the previous selection

                return {
                    'domain': {
                        'asset_account_id': [
                            ('code', 'like', '1%'),
                            ('asset_currency_id', '=', asset_account.asset_currency_id.id)
                        ]
                    }
                }
            else:
                return {
                    'domain': {
                        'asset_account_id': [
                            ('code', 'like', '1%')
                        ]
                    }
                }

    @api.onchange('discount_currency_id')
    def _onchange_sales_currency_id(self):
        """Updates the domain for account_id based on the selected currency."""
        for discount in self:
            if discount.discount_currency_id:
                discount.discount_currency_id = False  # Clear the previous selection

                return {
                    'domain': {
                        'sales_discount_id': [
                            ('account_type', 'like', 'discount'),
                            ('code', 'like', '5%'),
                            ('discount_currency_id', '=', discount.sales_discount_id.id)
                        ]
                    }
                }
            else:
                return {
                    'domain': {
                        'sales_discount_id': [
                            ('account_type', 'like', 'discount'),
                            ('code', 'like', '5%')
                        ]
                    }
                }

    @api.onchange('sales_currency_id')
    def _onchange_sales_currency_id(self):
        """Updates the domain for account_id based on the selected currency."""
        for sales_saft in self:
            if sales_saft.currency_id:
                sales_saft.sales_account_id = False  # Clear the previous selection

                return {
                    'domain': {
                        'sales_account_id': [
                            ('account_type', 'like', 'commission'),
                            ('code', 'like', '5%'),
                            ('sales_currency_id', '=', sales_saft.currency_id.id)
                        ]
                    }
                }
            else:
                return {
                    'domain': {
                        'sales_account_id': [
                            ('account_type', 'like', 'commission'),
                            ('code', 'like', '5%')
                        ]
                    }
                }

    @api.onchange('currency_id')
    def _onchange_currency_id(self):
        """Updates the domain for account_id based on the selected currency."""
        for employee in self:
            if employee.currency_id:
                employee.account_id = False  # Clear the previous selection

                return {
                    'domain': {
                        'account_id': [
                            ('account_type', 'like', 'commission'),
                            ('code', 'like', '5%'),
                            ('currency_id', '=', employee.currency_id.id)
                        ]
                    }
                }
            else:
                return {
                    'domain': {
                        'account_id': [
                            ('account_type', 'like', 'commission'),
                            ('code', 'like', '5%')
                        ]
                    }
                }

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
                    'my_product_id': product.id,
                    'name': product.name,
                    'default_code': product.internal_reference,
                    'type': product.detailed_type,
                    'list_price': product.sale_price,
                    'standard_price': product.cost,
                    'categ_id': product.category_id.id,

                    'pos_categ_ids': product.pos_categ_ids,
                    'uom_id': 1,
                    'available_in_pos': product.available_in_pos,
                    'image_1920': product.image_1920,
                })
            else:
                odoo_product.write({
                    'my_product_id': product.id,

                    'name': product.name,
                    'default_code': product.internal_reference,
                    'type': product.detailed_type,
                    'list_price': product.sale_price,
                    'standard_price': product.cost,
                    'categ_id': product.category_id.id,

                    'pos_categ_ids': product.pos_categ_ids,

                    'uom_id': 1,
                    'available_in_pos': product.available_in_pos,
                    'image_1920': product.image_1920,
                })
