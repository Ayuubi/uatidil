from odoo import models, fields


class ProductMovement(models.Model):
    _name = 'idil.product.movement'
    _description = 'Product Movement History'

    product_id = fields.Many2one('my_product.product', string='Product', required=True, ondelete='cascade')
    movement_type = fields.Selection([
        ('in', 'In'),
        ('out', 'Out')
    ], string='Movement Type', required=True)
    quantity = fields.Float(string='Quantity', required=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    source_document = fields.Char(string='Source Document')
    manufacturing_order_id = fields.Many2one('idil.manufacturing.order', string='Manufacturing Order')
    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Salesperson', required=True)
