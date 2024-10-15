import re

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import datetime


class SaleOrder(models.Model):
    _name = 'idil.sale.order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Sale Order'

    name = fields.Char(string='Sales Reference', tracking=True)

    sales_person_id = fields.Many2one('idil.sales.sales_personnel', string='Salesperson', required=True
                                      )
    # Add a reference to the salesperson's order
    salesperson_order_id = fields.Many2one('idil.salesperson.place.order', string='Related Salesperson Order',

                                           help="This field links to the salesperson order "
                                                "that this actual order is based on.")

    order_date = fields.Datetime(string='Order Date', default=fields.Datetime.now)
    order_lines = fields.One2many('idil.sale.order.line', 'order_id', string='Order Lines')
    order_total = fields.Float(string='Order Total', compute='_compute_order_total', store=True)
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')],
                             default='confirmed')

    commission_amount = fields.Float(
        string='Commission Amount',
        compute='_compute_total_commission',
        store=True
    )

    @api.depends('order_lines.quantity', 'order_lines.product_id.commission')
    def _compute_total_commission(self):
        for order in self:
            total_commission = 0.0
            for line in order.order_lines:
                product = line.product_id
                if product.is_sales_commissionable:
                    if not product.sales_account_id:
                        raise ValidationError(f"Product '{product.name}' does not have a Sales Commission Account set.")
                    if product.commission <= 0:
                        raise ValidationError(f"Product '{product.name}' does not have a valid Commission Rate set.")

                    # Calculate commission only if validations pass
                    total_commission += line.quantity * product.commission

            order.commission_amount = total_commission

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

            # Set order reference if not provided
            if 'name' not in vals or not vals['name']:
                vals['name'] = self._generate_order_reference(vals)

        # Proceed with creating the SaleOrder with the updated vals
        new_order = super(SaleOrder, self).create(vals)
        # Create a corresponding SalesReceipt
        self.env['idil.sales.receipt'].create({
            'sales_order_id': new_order.id,
            'due_amount': new_order.order_total,
            'paid_amount': 0,
            'remaining_amount': new_order.order_total,
            'salesperson_id': new_order.sales_person_id.id,

        })

        for line in new_order.order_lines:
            self.env['idil.product.movement'].create({
                'product_id': line.product_id.id,
                'movement_type': "out",
                'quantity': line.quantity * -1,
                'date': fields.Datetime.now(),
                'source_document': new_order.name,
                'sales_person_id': new_order.sales_person_id.id,
            })

        new_order.book_accounting_entry()

        return new_order

    def _generate_order_reference(self, vals):
        bom_id = vals.get('bom_id', False)
        if bom_id:
            bom = self.env['idil.bom'].browse(bom_id)
            bom_name = re.sub('[^A-Za-z0-9]+', '', bom.name[:2]).upper() if bom and bom.name else 'XX'
            date_str = '/' + datetime.now().strftime('%d%m%Y')
            day_night = '/DAY/' if datetime.now().hour < 12 else '/NIGHT/'
            sequence = self.env['ir.sequence'].next_by_code('idil.sale.order.sequence')
            sequence = sequence[-3:] if sequence else '000'
            return f"{bom_name}{date_str}{day_night}{sequence}"
        else:
            # Fallback if no BOM is provided
            return self.env['ir.sequence'].next_by_code('idil.sale.order.sequence')

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
                discount_quantity = (line.product_id.discount / 100) * (
                    line.quantity) if line.product_id.is_quantity_discount else 0.0

                order_lines_cmds.append((0, 0, {
                    'product_id': line.product_id.id,
                    'quantity_Demand': line.quantity,
                    'discount_quantity': discount_quantity,
                    'quantity': line.quantity,
                    # Set initial 'quantity' the same as 'quantity_Demand'
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

            # Define the expected currency from the salesperson's account receivable
            expected_currency = order.sales_person_id.account_receivable_id.currency_id

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
                product = line.product_id

                # Validate required accounts and currency consistency
                if line.commission_amount > 0:
                    if not product.sales_account_id:
                        raise ValidationError(
                            f"Product '{product.name}' has a commission amount but no Sales Commission Account set.")
                    if product.sales_account_id.currency_id != expected_currency:
                        raise ValidationError(
                            f"Sales Commission Account for product '{product.name}' has a different currency.\n"
                            f"Expected currency: {expected_currency.name}, "
                            f"Actual currency: {product.sales_account_id.currency_id.name}."
                        )

                if line.discount_amount > 0:
                    if not product.sales_discount_id:
                        raise ValidationError(
                            f"Product '{product.name}' has a discount amount but no Sales Discount Account set.")
                    if product.sales_discount_id.currency_id != expected_currency:
                        raise ValidationError(
                            f"Sales Discount Account for product '{product.name}' has a different currency.\n"
                            f"Expected currency: {expected_currency.name}, "
                            f"Actual currency: {product.sales_discount_id.currency_id.name}."
                        )

                if not product.asset_account_id:
                    raise ValidationError(f"Product '{product.name}' does not have an Asset Account set.")
                if product.asset_account_id.currency_id != expected_currency:
                    raise ValidationError(
                        f"Asset Account for product '{product.name}' has a different currency.\n"
                        f"Expected currency: {expected_currency.name}, "
                        f"Actual currency: {product.asset_account_id.currency_id.name}."
                    )

                # Check asset account balance for sufficiency
                asset_balance = self.env['idil.transaction_bookingline'].search([
                    ('account_number', '=', product.asset_account_id.id),
                ]).read_group(
                    [('account_number', '=', product.asset_account_id.id)],
                    ['dr_amount', 'cr_amount'],
                    ['account_number']
                )

                # Calculate current asset balance
                asset_balance_amount = sum(record['dr_amount'] - record['cr_amount'] for record in asset_balance)

                # Calculate total transaction amount that affects the asset account
                total_transaction_amount = line.subtotal + line.commission_amount + line.discount_amount

                if asset_balance_amount < total_transaction_amount:
                    raise ValidationError(
                        f"Insufficient balance in Asset Account for product '{product.name}'.\n"
                        f"Available balance: {asset_balance_amount}, Required: {total_transaction_amount}."
                    )

                if not product.income_account_id:
                    raise ValidationError(f"Product '{product.name}' does not have an Income Account set.")
                if product.income_account_id.currency_id != expected_currency:
                    raise ValidationError(
                        f"Income Account for product '{product.name}' has a different currency.\n"
                        f"Expected currency: {expected_currency.name}, "
                        f"Actual currency: {product.income_account_id.currency_id.name}."
                    )

                # Debit entry for the order line amount
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Sale of {product.name}',
                    'product_id': product.id,
                    'account_number': order.sales_person_id.account_receivable_id.id,
                    'transaction_type': 'dr',  # Debit transaction
                    'dr_amount': line.subtotal,
                    'cr_amount': 0,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })
                total_debit += line.subtotal

                # Credit entry using the product's income account
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Sales Revenue - {product.name}',
                    'product_id': product.id,
                    'account_number': product.income_account_id.id,
                    'transaction_type': 'cr',
                    'dr_amount': 0,
                    'cr_amount': line.subtotal,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })

                # Credit entry asset inventory account of the product
                self.env['idil.transaction_bookingline'].create({
                    'transaction_booking_id': transaction_booking.id,
                    'description': f'Sales Inventory account for - {product.name}',
                    'product_id': product.id,
                    'account_number': product.asset_account_id.id,
                    'transaction_type': 'cr',
                    'dr_amount': 0,
                    'cr_amount': total_transaction_amount,
                    'transaction_date': fields.Date.context_today(self),
                    # Include other necessary fields
                })

                # Debit entry for commission expenses
                if product.is_sales_commissionable and line.commission_amount > 0:
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': transaction_booking.id,
                        'description': f'Commission Expense - {product.name}',
                        'product_id': product.id,
                        'account_number': product.sales_account_id.id,
                        'transaction_type': 'dr',  # Debit transaction for commission expense
                        'dr_amount': line.commission_amount,
                        'cr_amount': 0,
                        'transaction_date': fields.Date.context_today(self),
                        # Include other necessary fields
                    })

                # Debit entry for discount expenses
                if line.discount_amount > 0:
                    self.env['idil.transaction_bookingline'].create({
                        'transaction_booking_id': transaction_booking.id,
                        'description': f'Discount Expense - {product.name}',
                        'product_id': product.id,
                        'account_number': product.sales_discount_id.id,
                        'transaction_type': 'dr',  # Debit transaction for discount expense
                        'dr_amount': line.discount_amount,
                        'cr_amount': 0,
                        'transaction_date': fields.Date.context_today(self),
                        # Include other necessary fields
                    })

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
    discount_amount = fields.Float(string='Discount Amount', compute='_compute_discount_amount', store=True)

    subtotal = fields.Float(string='Due Amount', compute='_compute_subtotal')

    # New computed field for commission amount
    commission_amount = fields.Float(string='Commission Amount', compute='_compute_commission_amount', store=True)

    # New computed field for Discount amount
    discount_quantity = fields.Float(string='Discount Quantity', compute='_compute_discount_quantity', store=True)

    @api.depends('quantity', 'product_id.commission')
    def _compute_commission_amount(self):
        for line in self:
            product = line.product_id
            if product.is_sales_commissionable:
                if not product.sales_account_id:
                    raise ValidationError(f"Product '{product.name}' does not have a Sales Commission Account set.")
                if product.commission <= 0:
                    raise ValidationError(f"Product '{product.name}' does not have a valid Commission Rate set.")

                # Calculate commission amount
                line.commission_amount = (line.quantity - line.discount_quantity) * product.commission
            else:
                line.commission_amount = 0.0

    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = (line.quantity * line.price_unit) - (
                    line.discount_quantity * line.price_unit) - line.commission_amount

    @api.depends('quantity')
    def _compute_discount_quantity(self):
        for line in self:
            line.discount_quantity = (line.product_id.discount / 100) * (
                line.quantity) if line.product_id.is_quantity_discount else 0.0

    @api.depends('discount_quantity', 'price_unit')
    def _compute_discount_amount(self):
        for line in self:
            line.discount_amount = line.discount_quantity * line.price_unit

    @api.depends('quantity_Demand', 'quantity')
    def _compute_quantity_diff(self):
        for record in self:
            record.quantity_diff = (record.quantity_Demand - record.quantity)

    @api.model
    def create(self, vals):
        record = super(SaleOrderLine, self).create(vals)

        # Create a Salesperson Transaction
        if record.order_id.sales_person_id:
            self.env['idil.salesperson.transaction'].create({
                'sales_person_id': record.order_id.sales_person_id.id,
                'date': fields.Date.today(),
                'order_id': record.order_id.id,
                'transaction_type': 'out',  # Assuming 'out' for sales
                'amount': record.subtotal + record.discount_amount + record.commission_amount,
                'description': f"Sales Amount of - Order Line for {record.product_id.name} (Qty: {record.quantity})"
            })
            self.env['idil.salesperson.transaction'].create({
                'sales_person_id': record.order_id.sales_person_id.id,
                'date': fields.Date.today(),
                'order_id': record.order_id.id,
                'transaction_type': 'in',  # Assuming 'out' for sales
                'amount': record.commission_amount,
                'description': f"Sales Commission Amount of - Order Line for  {record.product_id.name} (Qty: {record.quantity})"
            })
            self.env['idil.salesperson.transaction'].create({
                'sales_person_id': record.order_id.sales_person_id.id,
                'date': fields.Date.today(),
                'order_id': record.order_id.id,
                'transaction_type': 'in',  # Assuming 'out' for sales
                'amount': record.discount_amount,
                'description': f"Sales Discount Amount of - Order Line for  {record.product_id.name} (Qty: {record.quantity})"
            })

        self.update_product_stock(record.product_id, record.quantity)
        return record

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
