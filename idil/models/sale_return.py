from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SaleReturn(models.Model):
    _name = 'idil.sale.return'
    _description = 'Sale Return'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    salesperson_id = fields.Many2one('idil.sales.sales_personnel', string='Salesperson', required=True)
    sale_order_id = fields.Many2one('idil.sale.order', string='Sale Order', required=True,
                                    domain="[('sales_person_id', '=', salesperson_id)]",
                                    help="Select a sales order related to the chosen salesperson.")
    return_date = fields.Datetime(string='Return Date', default=fields.Datetime.now, required=True)
    return_lines = fields.One2many('idil.sale.return.line', 'return_id', string='Return Lines', required=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancelled', 'Cancelled')],
                             default='draft', string='Status', track_visibility='onchange')

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        if not self.sale_order_id:
            return
        sale_order = self.sale_order_id
        return_lines = [(5, 0, 0)]  # Clear existing lines

        for line in sale_order.order_lines:
            return_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'quantity': line.quantity,  # Ensure this is being set
                'returned_quantity': 0.0,
                'price_unit': line.price_unit,
                'subtotal': line.subtotal,
            }))

        self.return_lines = return_lines

    def action_confirm(self):
        for return_order in self:
            if return_order.state != 'draft':
                raise UserError("Only draft return orders can be confirmed.")

            for return_line in return_order.return_lines:
                corresponding_sale_line = self.env['idil.sale.order.line'].search([
                    ('order_id', '=', return_order.sale_order_id.id),
                    ('product_id', '=', return_line.product_id.id)
                ], limit=1)

                if corresponding_sale_line:
                    if return_line.returned_quantity > corresponding_sale_line.quantity:
                        raise ValidationError(
                            f"Returned quantity for {return_line.product_id.name} exceeds the original quantity."
                        )
                    corresponding_sale_line.quantity -= return_line.returned_quantity
                    # Implement the method to update product stock if needed
                    # self.update_product_stock(return_line.product_id, return_line.returned_quantity)
                    # Book the transaction in the transaction booking table
            self.book_sales_return_entry()

            return_order.state = 'confirmed'

    def book_sales_return_entry(self):
        for return_order in self:
            if not return_order.salesperson_id.account_receivable_id:
                raise ValidationError("The salesperson does not have a receivable account set.")

            # Define the expected currency from the salesperson's account receivable
            expected_currency = return_order.salesperson_id.account_receivable_id.currency_id

            # Create a transaction booking for the return
            transaction_booking = self.env['idil.transaction_booking'].create({
                'sales_person_id': return_order.salesperson_id.id,
                'sale_order_id': return_order.sale_order_id.id,  # Link to the original SaleOrder's ID
                'trx_source_id': 3,
                'Sales_order_number': return_order.sale_order_id.id,
                'payment_method': 'bank_transfer',  # Assuming default payment method; adjust as needed
                'payment_status': 'pending',  # Assuming initial payment status; adjust as needed
                'trx_date': fields.Date.context_today(self),
                'amount': sum(line.subtotal for line in return_order.return_lines),
                # Include other necessary fields
            })

            for return_line in return_order.return_lines:
                product = return_line.product_id

                # Reversed Debit entry (now as Credit) for the return line amount
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Return of {product.name}',
                    'product_id': product.id,
                    'account_number': return_order.salesperson_id.account_receivable_id.id,
                    'transaction_type': 'cr',  # Reversed transaction (Credit)
                    'dr_amount': 0,
                    'cr_amount': return_line.subtotal,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })

                # Reversed Credit entry (now as Debit) using the product's income account
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Sales Return Revenue - {product.name}',
                    'product_id': product.id,
                    'account_number': product.income_account_id.id,
                    'transaction_type': 'dr',  # Reversed transaction (Debit)
                    'dr_amount': return_line.subtotal,
                    'cr_amount': 0,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })

                # Reversed Credit entry (now as Debit) for asset inventory account of the product
                total_transaction_amount = return_line.subtotal  # Add commission and discount if applicable
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Sales Inventory Return for - {product.name}',
                    'product_id': product.id,
                    'account_number': product.asset_account_id.id,
                    'transaction_type': 'dr',  # Reversed transaction (Debit)
                    'dr_amount': total_transaction_amount,
                    'cr_amount': 0,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })

                # Reversed Debit entry (now as Credit) for commission expenses

                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Return Commission Expense - {product.name}',
                    'product_id': product.id,
                    'account_number': product.sales_account_id.id,
                    'transaction_type': 'cr',  # Reversed transaction (Credit)
                    'dr_amount': 0,
                    'cr_amount': total_transaction_amount,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })

                # Reversed Debit entry (now as Credit) for discount expenses

                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Return Discount Expense - {product.name}',
                    'product_id': product.id,
                    'account_number': product.sales_discount_id.id,
                    'transaction_type': 'cr',  # Reversed transaction (Credit)
                    'dr_amount': 0,
                    'cr_amount': total_transaction_amount,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })


class SaleReturnLine(models.Model):
    _name = 'idil.sale.return.line'
    _description = 'Sale Return Line'

    return_id = fields.Many2one('idil.sale.return', string='Sale Return', required=True, ondelete='cascade')
    product_id = fields.Many2one('my_product.product', string='Product', required=True)
    quantity = fields.Float(string='Original Quantity', required=True)
    returned_quantity = fields.Float(string='Returned Quantity', required=True)
    price_unit = fields.Float(string='Unit Price', required=True)
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)

    @api.depends('returned_quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.returned_quantity * line.price_unit
