from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _name = 'idil.sale.order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Sale Order'

    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Salesperson', required=True
                                      )
    # Add a reference to the salesperson's order
    salesperson_order_id = fields.Many2one('idil.salesperson.place.order', string='Related Salesperson Order',

                                           help="This field links to the salesperson order "
                                                "that this actual order is based on.")

    order_date = fields.Datetime(string='Order Date', default=fields.Datetime.now)
    order_lines = fields.One2many('idil.sale.order.line', 'order_id', string='Order Lines')
    order_total = fields.Float(string='Order Total', compute='_compute_order_total', store=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')], default='draft')

    @api.model
    def create(self, vals):
        # Step 1: Check if sales_person_id is provided in vals
        if 'sales_person_id' in vals:
            salesperson_id = vals['sales_person_id']

            # Step 2: Find the most recent draft SalespersonOrder for this salesperson
            salesperson_order = self.env['idil.salesperson.place.order'].search([
                ('salesperson_id', '=', salesperson_id),
                ('state', '=', 'draft')
            ], order='order_date desc', limit=1)

            if salesperson_order:
                # Link the found SalespersonOrder to the SaleOrder being created
                vals['salesperson_order_id'] = salesperson_order.id
                salesperson_order.write({'state': 'confirmed'})
            else:
                # Optionally handle the case where no draft SalespersonOrder is found
                raise UserError("No draft SalespersonOrder found for the given salesperson.")

        # Proceed with creating the SaleOrder with the updated vals
        new_order = super(SaleOrder, self).create(vals)
        new_order.book_accounting_entry()

        return new_order

    @api.depends('order_lines.subtotal')
    def _compute_order_total(self):
        for order in self:
            order.order_total = sum(order.order_lines.mapped('subtotal'))

    @api.onchange('sales_person_id')
    def _onchange_sales_person_id(self):
        if not self.sales_person_id:
            return
        # Assuming 'order_date' is the field name for the order's date in both models
        current_order_date = fields.Date.today()  # Adjust if the order date is not today

        last_order = self.env['idil.salesperson.place.order'].search([
            ('salesperson_id', '=', self.sales_person_id.id),
            ('state', '=', 'draft')], order='order_date desc', limit=1)

        if last_order:
            # Check if the last order's date is the same as the current order's date
            last_order_date = fields.Date.to_date(last_order.order_date)
            if last_order_date != current_order_date:
                raise UserError(
                    "The salesperson's last draft order date does not match today's date. "
                    "Orders can only be created based on the last order if they occur on the same date.")

            # Prepare a list of commands to update 'order_lines' one2many field
            order_lines_cmds = [(5, 0, 0)]  # Command to delete all existing records in the set
            for line in last_order.order_lines:
                order_lines_cmds.append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity_Demand': line.quantity,
                    'quantity': line.quantity,  # Set initial 'quantity' the same as 'quantity_Demand'
                    # Add other necessary fields here
                }))

            # Apply the commands to the 'order_lines' field
            self.order_lines = order_lines_cmds

        else:
            raise UserError("This salesperson does not have any draft orders to reference.")

    def book_accounting_entry(self):
        for order in self:
            if not order.sales_person_id.account_receivable_id:
                raise ValidationError("The salesperson does not have a receivable account set.")

            # Create a transaction booking
            transaction_booking = self.env['idil.transaction_booking'].create({
                'sales_person_id': order.sales_person_id.id,
                'sale_order_id': order.id,  # Set the sale_order_id to the current SaleOrder's ID
                'trx_source_id': 3,
                'Sales_order_number': order.id,
                'payment_method': 'bank_transfer',  # Assuming default payment method; adjust as needed
                'payment_status': 'pending',  # Assuming initial payment status; adjust as needed
                'trx_date': fields.Date.context_today(self),
                'amount': order.order_total,
                # Include other necessary fields
            })

            total_debit = 0
            # For each order line, create a booking line entry for debit
            for line in order.order_lines:
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Sale of {line.product_id.name}',
                    'product_id': line.product_id.id,
                    'account_number': order.sales_person_id.account_receivable_id.id,
                    'transaction_type': 'dr',  # Debit transaction
                    'dr_amount': line.subtotal,
                    'cr_amount': 0,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })
                total_debit += line.subtotal

                # Credit entry using the product's income account
                if line.product_id.income_account_id:
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': transaction_booking.id,
                        'description': f'Sales Revenue - {line.product_id.name}',
                        'product_id': line.product_id.id,
                        'account_number': line.product_id.income_account_id.id,
                        'transaction_type': 'cr',
                        'dr_amount': 0,
                        'cr_amount': line.subtotal,
                        'transaction_date': fields.Date.context_today(self),
                        # Include other necessary fields
                    })
                else:
                    raise ValidationError(f"Product {line.product_id.name} does not have an income account set.")

    def write(self, vals):
        # Call the original write method
        res = super(SaleOrder, self).write(vals)
        # After the write operation, update booking entries if necessary
        self.update_booking_entry()
        return res

    def update_booking_entry(self):
        # Find the related TransactionBooking record
        booking = self.env['idil.transaction_booking'].search([('sale_order_id', '=', self.id)], limit=1)
        if booking:
            booking.amount = self.order_total
            booking.update_related_booking_lines()

    def unlink(self):
        # Collect salesperson orders before deletion to ensure they are available for state update
        salesperson_orders = self.mapped('salesperson_order_id').filtered(lambda r: r.state == 'confirmed')

        for order in self:
            # Adjust product stock quantities for each order line before deletion
            for line in order.order_lines:
                if line.product_id:
                    # Assuming SaleOrderLine has a method 'update_product_stock' to adjust stock quantities
                    SaleOrderLine.update_product_stock(line.product_id, -line.quantity)

        # Revert the state of related SalespersonOrder(s) back to 'draft'
        salesperson_orders.write({'state': 'draft'})

        # Proceed to delete the SaleOrder(s) after adjustments
        return super(SaleOrder, self).unlink()


class SaleOrderLine(models.Model):
    _name = 'idil.sale.order.line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Sale Order Line'

    order_id = fields.Many2one('idil.sale.order', string='Sale Order')
    product_id = fields.Many2one('my_product.product', string='Product')
    quantity_Demand = fields.Float(string='Demand', default=1.0)
    quantity = fields.Float(string='Quantity Used', required=True, tracking=True)
    # New computed field for the difference between Demand and Quantity Used
    quantity_diff = fields.Float(string='Quantity Difference', compute='_compute_quantity_diff', store=True)

    price_unit = fields.Float(string='Unit Price', related='product_id.sale_price', store=True)
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal')

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    @api.depends('quantity_Demand', 'quantity')
    def _compute_quantity_diff(self):
        for record in self:
            record.quantity_diff = record.quantity_Demand - record.quantity

    @api.model
    def create(self, vals):
        result = super(SaleOrderLine, self).create(vals)
        # Update stock quantity after creating the sale order line without checking product type
        self.update_product_stock(result.product_id, result.quantity)
        return result

    def write(self, vals):
        if 'quantity' in vals:
            # Calculate the difference in quantity to adjust the stock, without checking product type
            quantity_diff = vals.get('quantity', self.quantity) - self.quantity
            self.update_product_stock(self.product_id, quantity_diff)
        return super(SaleOrderLine, self).write(vals)

    @staticmethod
    def update_product_stock(product, quantity_diff):
        """Static Method: Update product stock quantity based on the sale order line quantity change."""
        new_stock_quantity = product.stock_quantity - quantity_diff
        if new_stock_quantity < 0:
            raise ValidationError(
                "Insufficient stock for product '{}'. The available stock quantity is {:.2f}, "
                "but the required quantity is {:.2f}."
                .format(product.name, product.stock_quantity, abs(quantity_diff))
            )
        product.stock_quantity = new_stock_quantity
