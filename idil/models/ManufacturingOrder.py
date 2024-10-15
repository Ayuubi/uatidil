from odoo import models, fields, api, exceptions
from datetime import datetime
from datetime import date
import re
from odoo.exceptions import ValidationError, UserError
import logging

_logger = logging.getLogger(__name__)


class ManufacturingOrder(models.Model):
    _name = 'idil.manufacturing.order'
    _description = 'Manufacturing Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Order Reference', tracking=True)
    bom_id = fields.Many2one('idil.bom', string='Bill of Materials', required=True,
                             help='Select the BOM for this manufacturing order', tracking=True)
    product_id = fields.Many2one('my_product.product', string='Product', required=True, readonly=True)

    product_qty = fields.Float(string='Product Quantity', default=1, required=True,
                               help="Quantity of the final product to be produced", tracking=True)
    product_cost = fields.Float(string='Product Cost Total', compute='_compute_product_cost_total', store=True,
                                readonly=True)
    manufacturing_order_line_ids = fields.One2many('idil.manufacturing.order.line', 'manufacturing_order_id',
                                                   string='Manufacturing Order Lines')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], default='draft', string='Status', tracking=True)
    scheduled_start_date = fields.Datetime(string='Scheduled Start Date', tracking=True, required=True)
    bom_grand_total = fields.Float(string='BOM Grand Total', compute='_compute_grand_total', store=True, readonly=True)
    tfg_qty = fields.Float(string='TFG Quantity', compute='_compute_tfg_qty', store=True, readonly=True)

    commission_employee_id = fields.Many2one(
        'idil.employee',
        string='Commission Employee',
        help='Select the employee who will receive the commission for this product'
    )

    # Commission fields
    commission_amount = fields.Float(string='Commission Amount', digits=(16, 5), compute='_compute_commission_amount',
                                     store=True)
    transaction_booking_id = fields.Many2one('idil.transaction_booking', string='Transaction Booking', readonly=True)
    # Currency fields
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env['res.currency'].browse(144),
        readonly=True
    )
    rate = fields.Float(string='Exchange Rate', compute='_compute_exchange_rate', store=True, readonly=True)

    @api.depends('currency_id')
    def _compute_exchange_rate(self):
        for order in self:
            if order.currency_id:
                rate = self.env['res.currency.rate'].search([
                    ('currency_id', '=', order.currency_id.id),
                    ('name', '=', fields.Date.today()),
                    ('company_id', '=', self.env.company.id)
                ], limit=1)
                order.rate = rate.rate if rate else 0.0
            else:
                order.rate = 0.0

    @api.constrains('currency_id')
    def _check_exchange_rate_exists(self):
        for order in self:
            if order.currency_id:
                rate = self.env['res.currency.rate'].search_count([
                    ('currency_id', '=', order.currency_id.id),
                    ('name', '=', fields.Date.today()),
                    ('company_id', '=', self.env.company.id)
                ])
                if rate == 0:
                    raise exceptions.ValidationError(
                        "No exchange rate found for today. Please insert today's rate before saving.")

    @api.depends('product_id', 'product_qty', 'commission_employee_id')
    def _compute_commission_amount(self):
        for order in self:
            _logger.info(f"Computing commission for order {order.name}")

            if order.product_id:
                _logger.info(f"Product ID: {order.product_id.id}, Product Name: {order.product_id.name}")

                if order.product_id.account_id:
                    _logger.info(f"Product has commission account: {order.product_id.account_id.name}")

                    if order.product_id.is_commissionable:
                        _logger.info("Product is commissionable")

                        employee = order.commission_employee_id
                        if employee:
                            _logger.info(
                                f"Commission Employee: {employee.name}, Commission Percentage: {employee.commission}")

                            commission_percentage = employee.commission
                            commission_amount = 0.0

                            # Loop through each item in the order
                            for line in order.manufacturing_order_line_ids:
                                item = line.item_id
                                if item.is_commission:
                                    _logger.info(f"Item {item.name} has commission flag set to True")
                                    # Calculate commission for the item based on quantity
                                    item_commission = commission_percentage * line.quantity
                                    commission_amount += item_commission

                            order.commission_amount = commission_amount
                            _logger.info(f"Total Commission Amount: {order.commission_amount}")
                        else:
                            _logger.info("No commission employee assigned")
                            order.commission_amount = 0.0
                    else:
                        _logger.info("Product is not commissionable")
                        order.commission_amount = 0.0
                else:
                    _logger.info("Product does not have a commission account")
                    order.commission_amount = 0.0
            else:
                _logger.info("No product assigned")
                order.commission_amount = 0.0

    @api.depends('manufacturing_order_line_ids.quantity')
    def _compute_tfg_qty(self):
        for order in self:
            tfg_items_qty = sum(line.quantity for line in order.manufacturing_order_line_ids if line.item_id.is_tfg)
            order.tfg_qty = order.product_qty / (tfg_items_qty if tfg_items_qty else 1)

    def check_items_expiration(self):
        """Check if any item in the manufacturing order has expired."""
        # Ensure the check is performed on specific order(s)
        for order in self:
            expired_items = []
            for line in order.manufacturing_order_line_ids:
                item = line.item_id
                if item.expiration_date and item.expiration_date < date.today():
                    expired_items.append(item.name)

            if expired_items:
                # Joining the list of expired items names to include in the error message
                expired_items_str = ", ".join(expired_items)
                raise ValidationError(
                    f"Cannot complete the order as the following items have expired: {expired_items_str}. "
                    f"Please update the BOM or the items before proceeding.")

    @api.onchange('bom_id')
    def onchange_bom_id(self):
        if self.bom_id:
            # Assuming 'idil.bom' has a 'product_id' field that references the product
            self.product_id = self.bom_id.product_id

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        if not self.bom_id or not self.product_qty:
            return

        # Ensure product_id is set from bom_id
        if self.bom_id and not self.product_id:
            self.product_id = self.bom_id.product_id

        # Mapping of BOM item IDs to their quantities for easy lookup
        bom_quantities = {line.Item_id.id: line.quantity for line in self.bom_id.bom_line_ids}

        for line in self.manufacturing_order_line_ids:
            if line.item_id.id in bom_quantities:
                # Calculate the new quantity for this item based on the product_qty
                new_quantity = bom_quantities[line.item_id.id] * self.product_qty

                # Update the line's quantity directly. Since we're in an onchange method,
                # these changes are temporary and reflected in the UI.
                line.quantity = new_quantity
                line.quantity_bom = new_quantity

        # Recalculate commission
        self._compute_commission_amount()

    @api.onchange('commission_employee_id')
    def _onchange_commission_employee_id(self):
        # Ensure product_id is set from bom_id
        if self.bom_id and not self.product_id:
            self.product_id = self.bom_id.product_id

        # Recalculate commission
        self._compute_commission_amount()

    @api.depends('manufacturing_order_line_ids.row_total')
    def _compute_grand_total(self):
        for order in self:
            order.bom_grand_total = sum(
                line.row_total for line in order.manufacturing_order_line_ids)

    @api.depends('manufacturing_order_line_ids.row_total', 'product_qty')
    def _compute_product_cost_total(self):
        for order in self:
            self.check_items_expiration()
            order.product_cost = sum(line.row_total for line in order.manufacturing_order_line_ids)

    @api.onchange('bom_id')
    def _onchange_bom_id(self):
        self.check_items_expiration()
        if not self.bom_id:
            self.manufacturing_order_line_ids = [(5, 0, 0)]  # Command to delete existing lines
            return
        new_lines = []
        for line in self.bom_id.bom_line_ids:
            line_vals = {
                'item_id': line.Item_id.id,
                'quantity': line.quantity,
                'quantity_bom': line.quantity,
                'cost_price': line.Item_id.cost_price,
            }
            new_lines.append((0, 0, line_vals))
        self.manufacturing_order_line_ids = new_lines

    @api.model
    def create(self, vals):
        _logger.info("Creating Manufacturing Order with values: %s", vals)

        # Check BOM and product setup
        if 'bom_id' in vals:
            bom = self.env['idil.bom'].browse(vals['bom_id'])
            if bom and bom.product_id:
                vals['product_id'] = bom.product_id.id
                product = bom.product_id
                if product.account_id and not vals.get('commission_employee_id'):
                    raise ValidationError("The product has a commission account but no employee is selected.")

        # Set order reference if not provided
        if 'name' not in vals or not vals['name']:
            vals['name'] = self._generate_order_reference(vals)

        # Set status to done
        vals['status'] = 'done'

        # Create order
        order = super(ManufacturingOrder, self).create(vals)

        # Ensure valid asset accounts
        if not order.product_id.asset_account_id:
            raise ValidationError(f"The product '{order.product_id.name}' does not have a valid asset account.")
        for line in order.manufacturing_order_line_ids:
            if not line.item_id.asset_account_id:
                raise ValidationError(f"The item '{line.item_id.name}' does not have a valid asset account.")

        # Check if asset account balance is sufficient
        for line in order.manufacturing_order_line_ids:
            item_account_balance = self._get_account_balance(line.item_id.asset_account_id.id)
            required_balance = line.cost_price * line.quantity
            if item_account_balance < required_balance:
                raise ValidationError(
                    f"Insufficient balance in account for item '{line.item_id.name}'. "
                    f"Required: {required_balance}, Available: {item_account_balance}"
                )

        # Create transaction booking
        booking_lines = []
        for line in order.manufacturing_order_line_ids:
            if order.rate <= 0:
                raise ValidationError("Rate cannot be zero")

            cost_amount_usd = line.cost_price * line.quantity
            cost_amount_sos = cost_amount_usd * order.rate  # Use the rate field from the order

            _logger.debug(f"Using exchange rate: {order.rate}")
            _logger.debug(f"Cost amount in USD: {cost_amount_usd}, converted to SOS: {cost_amount_sos}")

            # Get clearing accounts
            source_clearing_account = self.env['idil.chart.account'].search(
                [('name', '=', 'Exchange Clearing Account'),
                 ('currency_id', '=', line.item_id.asset_account_id.currency_id.id)],
                limit=1)
            target_clearing_account = self.env['idil.chart.account'].search(
                [('name', '=', 'Exchange Clearing Account'),
                 ('currency_id', '=', order.product_id.asset_account_id.currency_id.id)],
                limit=1)

            if not source_clearing_account or not target_clearing_account:
                raise ValidationError("Exchange clearing accounts are required for currency conversion.")

            # Debit line for reducing raw material stock in product currency
            booking_lines.append((0, 0, {
                'order_line': len(booking_lines) + 1,
                'description': 'Manufacturing Order Transaction - Debit',
                'item_id': line.item_id.id,
                'product_id': order.product_id.id,
                'account_number': order.product_id.asset_account_id.id,
                'transaction_type': 'dr',
                'dr_amount': line.cost_amount_sos,
                'cr_amount': 0.0,
                'transaction_date': fields.Date.today(),
            }))

            # Credit the target clearing account for currency adjustment
            booking_lines.append((0, 0, {
                'order_line': len(booking_lines) + 1,
                'description': 'Manufacturing Order Transaction Exchange - Credit',
                'item_id': line.item_id.id,
                'product_id': order.product_id.id,
                'account_number': target_clearing_account.id,
                'transaction_type': 'cr',
                'dr_amount': 0.0,
                'cr_amount': line.cost_amount_sos,
                'transaction_date': fields.Date.today(),
            }))

            # Credit the source clearing account for currency adjustment
            booking_lines.append((0, 0, {
                'order_line': len(booking_lines) + 1,
                'description': 'Manufacturing Order Transaction Exchange - Debit',
                'item_id': line.item_id.id,
                'product_id': order.product_id.id,
                'account_number': source_clearing_account.id,
                'transaction_type': 'dr',
                'dr_amount': line.row_total,
                'cr_amount': 0.0,
                'transaction_date': fields.Date.today(),
            }))

            # Credit line for increasing product stock in item currency
            booking_lines.append((0, 0, {
                'order_line': len(booking_lines) + 1,
                'description': 'Manufacturing Order Transaction - Credit',
                'item_id': line.item_id.id,
                'product_id': order.product_id.id,
                'account_number': line.item_id.asset_account_id.id,
                'transaction_type': 'cr',
                'dr_amount': 0.0,
                'cr_amount': line.row_total,
                'transaction_date': fields.Date.today(),
            }))

        # Add commission booking lines if applicable
        if order.commission_amount > 0:
            if not order.product_id.account_id:
                raise ValidationError(
                    f"The product '{order.product_id.name}' does not have a valid commission account.")

            if order.product_id.account_id.currency_id != order.commission_employee_id.account_id.currency_id:
                raise ValidationError(
                    f"The currency for the product's account and the employee's commission account must be the same. "
                    f"Product Account Currency: {order.product_id.account_id.currency_id.name}, "
                    f"Employee Account Currency: {order.commission_employee_id.account_id.currency_id.name}."
                )

            booking_lines.append((0, 0, {
                'order_line': len(booking_lines) + 1,
                'description': 'Commission Expense',
                'product_id': order.product_id.id,
                'account_number': order.product_id.account_id.id,
                'transaction_type': 'dr',
                'dr_amount': order.commission_amount,
                'cr_amount': 0.0,
                'transaction_date': fields.Date.today(),
            }))

            if not order.commission_employee_id.account_id:
                raise ValidationError(
                    f"The employee '{order.commission_employee_id.name}' does not have a valid commission account.")

            booking_lines.append((0, 0, {
                'order_line': len(booking_lines) + 1,
                'description': 'Commission Liability',
                'product_id': order.product_id.id,
                'account_number': order.commission_employee_id.account_id.id,
                'transaction_type': 'cr',
                'dr_amount': 0.0,
                'cr_amount': order.commission_amount,
                'transaction_date': fields.Date.today(),
            }))

        transaction_booking = self.env['idil.transaction_booking'].create({
            'transaction_number': self.env['ir.sequence'].next_by_code('idil.transaction_booking'),
            'reffno': order.name,
            'order_number': order.name,
            'amount': order.product_cost,
            'trx_date': fields.Date.today(),
            'payment_status': 'paid',
            'booking_lines': booking_lines,
        })

        order.write({'transaction_booking_id': transaction_booking.id})

        # Increase the product's stock quantity based on the BOM
        if order and order.bom_id and order.bom_id.product_id:
            product = order.bom_id.product_id
            product.stock_quantity += order.product_qty
            product.write({'stock_quantity': product.stock_quantity})

        # Attempt to adjust stock levels
        try:
            for line in order.manufacturing_order_line_ids:
                if line.item_id.item_type == 'inventory':
                    if line.item_id.quantity < line.quantity:
                        raise ValidationError(
                            f"Insufficient stock for item '{line.item_id.name}'. Current stock: {line.item_id.quantity}, "
                            f"Requested: {line.quantity}"
                        )
                    with self.env.cr.savepoint():
                        line.item_id.with_context(update_transaction_booking=False).adjust_stock(line.quantity)
        except ValidationError as e:
            raise ValidationError(e.args[0])

        if order.commission_amount > 0:
            self.env['idil.commission'].create({
                'manufacturing_order_id': order.id,
                'employee_id': order.commission_employee_id.id,
                'commission_amount': order.commission_amount,
                'commission_paid': 0,
                'payment_status': "pending",
                'commission_remaining': order.commission_amount,
                'date': fields.Date.context_today(self),
            })

        self.env['idil.product.movement'].create({
            'product_id': order.product_id.id,  # Corrected reference to order.product_id
            'movement_type': "in",
            'quantity': order.product_qty,
            'date': fields.Datetime.now(),
            'source_document': order.name,  # Use order.name instead of self.name
        })

        return order

    def _get_account_balance(self, account_id):
        """Calculate the balance for an account."""
        self.env.cr.execute("""
                    SELECT COALESCE(SUM(dr_amount) - SUM(cr_amount), 0) as balance
                    FROM idil_transaction_bookingline
                    WHERE account_number = %s
                """, (account_id,))
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _generate_order_reference(self, vals):
        bom_id = vals.get('bom_id', False)
        if bom_id:
            bom = self.env['idil.bom'].browse(bom_id)
            bom_name = re.sub('[^A-Za-z0-9]+', '', bom.name[:2]).upper() if bom and bom.name else 'XX'
            date_str = '/' + datetime.now().strftime('%d%m%Y')
            day_night = '/DAY/' if datetime.now().hour < 12 else '/NIGHT/'
            sequence = self.env['ir.sequence'].next_by_code('idil.manufacturing.order.sequence')
            sequence = sequence[-3:] if sequence else '000'
            return f"{bom_name}{date_str}{day_night}{sequence}"
        else:
            # Fallback if no BOM is provided
            return self.env['ir.sequence'].next_by_code('idil.manufacturing.order.sequence')


# def write(self, vals):
#     for order in self:
#         # Ensure that the product has a commission account and an employee is selected
#         if 'commission_employee_id' in vals and order.product_id.account_id and not vals.get(
#                 'commission_employee_id'):
#             raise ValidationError("The product has a commission account but no employee is selected.")
#
#     # Track original quantities for both the final product and items in the order lines
#     self.check_items_expiration()
#     original_product_quantities = {order.id: order.product_qty for order in self}
#     original_item_quantities = {}
#     for order in self:
#         for line in order.manufacturing_order_line_ids:
#             original_item_quantities[line.id] = line.quantity
#
#     # Perform the actual update
#     result = super(ManufacturingOrder, self).write(vals)
#     for order in self:
#         # Ensure all items and the product have valid asset accounts
#         if not order.product_id.asset_account_id:
#             raise ValidationError(f"The product '{order.product_id.name}' does not have a valid asset account.")
#
#         for line in order.manufacturing_order_line_ids:
#             if not line.item_id.asset_account_id:
#                 raise ValidationError(f"The item '{line.item_id.name}' does not have a valid asset account.")
#
#         # Update transaction booking lines
#         booking_lines_to_update = order.transaction_booking_id.booking_lines
#
#         for line in order.manufacturing_order_line_ids:
#             debit_line = booking_lines_to_update.filtered(
#                 lambda bl: bl.transaction_type == 'dr' and bl.item_id == line.item_id)
#             credit_line = booking_lines_to_update.filtered(
#                 lambda bl: bl.transaction_type == 'cr' and bl.item_id == line.item_id)
#
#             if debit_line:
#                 debit_line.write({
#                     'dr_amount': line.cost_price * line.quantity,
#                     'cr_amount': 0.0,
#                 })
#             else:
#                 # Create new debit line if it doesn't exist
#                 order.transaction_booking_id.booking_lines.create({
#                     'order_line': len(booking_lines_to_update) + 1,
#                     'description': 'Manufacturing Order Transaction - Debit',
#                     'item_id': line.item_id.id,
#                     'product_id': order.product_id.id,
#                     'account_number': order.product_id.asset_account_id.id,
#                     'transaction_type': 'dr',
#                     'dr_amount': line.cost_price * line.quantity,
#                     'cr_amount': 0.0,
#                     'transaction_date': fields.Date.today(),
#                     'transaction_booking_id': order.transaction_booking_id.id,
#                 })
#
#             if credit_line:
#                 credit_line.write({
#                     'dr_amount': 0.0,
#                     'cr_amount': line.cost_price * line.quantity,
#                 })
#             else:
#                 # Create new credit line if it doesn't exist
#                 order.transaction_booking_id.booking_lines.create({
#                     'order_line': len(booking_lines_to_update) + 1,
#                     'description': 'Manufacturing Order Transaction - Credit',
#                     'item_id': line.item_id.id,
#                     'product_id': order.product_id.id,
#                     'account_number': line.item_id.asset_account_id.id,
#                     'transaction_type': 'cr',
#                     'dr_amount': 0.0,
#                     'cr_amount': line.cost_price * line.quantity,
#                     'transaction_date': fields.Date.today(),
#                     'transaction_booking_id': order.transaction_booking_id.id,
#                 })
#
#         # Update commission booking lines
#         if order.commission_amount > 0:
#             debit_commission_line = booking_lines_to_update.filtered(
#                 lambda bl: bl.transaction_type == 'dr' and bl.description == 'Commission Expense')
#             credit_commission_line = booking_lines_to_update.filtered(
#                 lambda bl: bl.transaction_type == 'cr' and bl.description == 'Commission Liability')
#
#             if debit_commission_line:
#                 debit_commission_line.write({
#                     'dr_amount': order.commission_amount,
#                     'cr_amount': 0.0,
#                 })
#             else:
#                 # Create new debit commission line if it doesn't exist
#                 order.transaction_booking_id.booking_lines.create({
#                     'order_line': len(booking_lines_to_update) + 1,
#                     'description': 'Commission Expense',
#                     'product_id': order.product_id.id,
#                     'account_number': order.product_id.account_id.id,
#                     'transaction_type': 'dr',
#                     'dr_amount': order.commission_amount,
#                     'cr_amount': 0.0,
#                     'transaction_date': fields.Date.today(),
#                     'transaction_booking_id': order.transaction_booking_id.id,
#                 })
#
#             if credit_commission_line:
#                 credit_commission_line.write({
#                     'dr_amount': 0.0,
#                     'cr_amount': order.commission_amount,
#                 })
#             else:
#                 # Create new credit commission line if it doesn't exist
#                 order.transaction_booking_id.booking_lines.create({
#                     'order_line': len(booking_lines_to_update) + 1,
#                     'description': 'Commission Liability',
#                     'product_id': order.product_id.id,
#                     'account_number': order.commission_employee_id.account_id.id,
#                     'transaction_type': 'cr',
#                     'dr_amount': 0.0,
#                     'cr_amount': order.commission_amount,
#                     'transaction_date': fields.Date.today(),
#                     'transaction_booking_id': order.transaction_booking_id.id,
#                 })
#
#     for order in self:
#         # Adjusting final product stock
#         original_product_qty = original_product_quantities.get(order.id, 0)
#         new_product_qty = order.product_qty
#         product_qty_difference = new_product_qty - original_product_qty
#         if product_qty_difference != 0 and order.bom_id and order.bom_id.product_id:
#             product = order.bom_id.product_id
#             new_stock_quantity = product.stock_quantity + product_qty_difference
#
#             # Check if the new stock quantity would be negative
#             if new_stock_quantity < 0:
#                 raise ValidationError(
#                     "Cannot adjust product stock for '{}' as it would result in a negative stock quantity.".format(
#                         product.name)
#                 )
#
#             # Update the product's stock quantity if it's not negative
#             product.write({'stock_quantity': new_stock_quantity})
#         # Adjusting item stock based on line changes
#         for line in order.manufacturing_order_line_ids:
#             original_qty = original_item_quantities.get(line.id, 0)
#             new_qty = line.quantity
#             qty_difference = new_qty - original_qty
#             if qty_difference != 0:
#                 try:
#                     # Assuming adjust_stock method exists for items to handle stock adjustments
#                     line.item_id.adjust_stock(qty_difference)
#                 except ValidationError as e:
#                     raise ValidationError(e.args[0])
#
#         if order.commission_amount > 0:
#             existing_commission = self.env['idil.commission'].search([('manufacturing_order_id', '=', order.id)])
#             if existing_commission:
#                 existing_commission.write({
#                     'employee_id': order.commission_employee_id.id,
#                     'commission_amount': order.commission_amount,
#                     'date': fields.Date.context_today(self),
#                 })
#
#     return result
#
# def unlink(self):
#     for order in self:
#         _logger.info("Unlink called on ManufacturingOrder with IDs: %s", self.ids)
#         if order.product_id and order.product_qty:
#             new_qty = order.product_id.stock_quantity - order.product_qty
#             if new_qty < 0:
#                 raise ValidationError(
#                     "Cannot delete order as it would result in negative stock for product %s." % order.product_id.name)
#             order.product_id.write({'stock_quantity': new_qty})
#
#         commissions = self.env['idil.commission'].search([('manufacturing_order_id', '=', order.id)])
#         commissions.unlink()
#     return super(ManufacturingOrder, self).unlink()


class ManufacturingOrderLine(models.Model):
    _name = 'idil.manufacturing.order.line'
    _description = 'Manufacturing Order Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    manufacturing_order_id = fields.Many2one('idil.manufacturing.order', string='Manufacturing Order', required=True,
                                             tracking=True)
    item_id = fields.Many2one('idil.item', string='Item', required=True, tracking=True)
    quantity_bom = fields.Float(string='Demand', digits=(16, 5), required=True, tracking=True)

    quantity = fields.Float(string='Quantity Used', digits=(16, 5), required=True, tracking=True)
    cost_price = fields.Float(string='Cost Price at Production', digits=(16, 5), required=True, tracking=True,
                              store=True)

    row_total = fields.Float(string='USD Total', digits=(16, 5), compute='_compute_row_total', store=True)
    cost_amount_sos = fields.Float(string='SOS Total', digits=(16, 5), compute='_compute_cost_amount_sos', store=True)

    # New computed field for the difference between Demand and Quantity Used
    quantity_diff = fields.Float(string='Quantity Difference', digits=(16, 5), compute='_compute_quantity_diff',
                                 store=True)

    @api.depends('row_total', 'manufacturing_order_id.rate')
    def _compute_cost_amount_sos(self):
        for line in self:
            if line.manufacturing_order_id:
                line.cost_amount_sos = line.row_total * line.manufacturing_order_id.rate

    @api.model
    def create(self, vals):
        record = super(ManufacturingOrderLine, self).create(vals)
        record._check_min_order_qty()

        # Create an item movement entry
        if record.item_id:
            self.env['idil.item.movement'].create({
                'item_id': record.item_id.id,
                'date': fields.Date.today(),
                'quantity': record.quantity * -1,
                'source': 'Inventory',
                'destination': 'Manufacturing',
                'movement_type': 'out',
                'related_document': f'idil.manufacturing.order.line,{record.id}'
            })

        return record

    def write(self, vals):
        result = super(ManufacturingOrderLine, self).write(vals)
        self._check_min_order_qty()
        return result

    def _check_min_order_qty(self):
        for line in self:
            if line.quantity <= line.item_id.min:
                # This is where you decide how to notify the user. For now, let's log a message.
                # Consider replacing this with a call to a custom notification system if needed.
                _logger.info(
                    f"Attention: The quantity for item '{line.item_id.name}' in manufacturing order '{line.item_id.name}' is near or below the minimum order quantity.")

    @api.depends('quantity_bom', 'quantity')
    def _compute_quantity_diff(self):
        for record in self:
            record.quantity_diff = record.quantity_bom - record.quantity

    @api.depends('quantity', 'cost_price')
    def _compute_row_total(self):
        for line in self:
            line.row_total = line.quantity * line.cost_price

    def unlink(self):
        # Loop through each line that is being deleted
        for line in self:
            # Check if the line has an item and quantity associated with it
            if line.item_id and line.quantity:
                # Adjust the item's stock level, adding back the quantity since the line is being deleted
                try:
                    # Increase stock by the quantity of the deleted line
                    line.item_id.adjust_stock(-line.quantity)
                except ValidationError as e:
                    # Handle any validation errors (e.g., stock adjustment issues)
                    raise ValidationError(e.args[0])  # e.args[0] contains the error message string

        # Call the super method to actually delete the lines after adjusting stock levels
        return super(ManufacturingOrderLine, self).unlink()
