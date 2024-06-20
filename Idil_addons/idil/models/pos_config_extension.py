from odoo import models, fields


class PosConfig(models.Model):
    _inherit = 'pos.config'

    available_my_products_ids = fields.Many2many('my_product.product', string='Available My Products')
