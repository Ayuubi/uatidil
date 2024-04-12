from odoo import models, fields, api


class PosScreen(models.Model):
    _name = 'my_pos.screen'
    _description = 'Point of Sale Screen'

    product_id = fields.Many2one('my_product.product', string='Product', required=True)
    customer_id = fields.Many2one('idil.customer.registration', string='Customer')
    quantity = fields.Float(string='Quantity', default=1.0)
    sale_price = fields.Float(string='Sales Price', compute='_compute_sale_price', store=True)
    total_price = fields.Float(string='Total Price', compute='_compute_total_price', store=True)

    @api.depends('product_id', 'quantity')
    def _compute_sale_price(self):
        for record in self:
            record.sale_price = record.product_id.sale_price * record.quantity

    @api.depends('sale_price')
    def _compute_total_price(self):
        for record in self:
            record.total_price = record.sale_price

    def process_sale(self):
        # Logic to process the sale
        # Example: Create a sale order
        sale_order = self.env['sale.order'].create({
            'partner_id': self.customer_id.id,
            # Add other fields as necessary
        })
        # Example: Add sale order lines
        sale_order_line = self.env['sale.order.line'].create({
            'order_id': sale_order.id,
            'product_id': self.product_id.id,
            'product_uom_qty': self.quantity,
            'price_unit': self.product_id.sale_price,
            # Add other fields as necessary
        })
        # Example: Update stock quantities
        self.product_id.stock_quantity -= self.quantity
