from odoo import models, fields, api
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

    name = fields.Char(string='Order Reference', required=True, tracking=True)
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
                    f"Cannot complete the order as the following items have expired: {expired_items_str}. Please update the BOM or the items before proceeding.")

    @api.onchange('bom_id')
    def onchange_bom_id(self):
        if self.bom_id:
            # Assuming 'idil.bom' has a 'product_id' field that references the product
            self.product_id = self.bom_id.product_id

    @api.onchange('product_qty')
    def _onchange_product_qty(self):
        if not self.bom_id or not self.product_qty:
            return

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

                # If you need to adjust cost_price and row_total as well, do it here.
                # Example:
                # line.cost_price = line.item_id.cost_price  # Adjust if the cost price is dynamic.
                # line.row_total = new_quantity * line.cost_price  # Assuming row_total needs to be recalculated.

    @api.depends('manufacturing_order_line_ids.row_total')
    def _compute_grand_total(self):
        for order in self:
            order.bom_grand_total = sum(
                line.row_total for line in order.manufacturing_order_line_ids)

    @api.depends('manufacturing_order_line_ids.row_total', 'product_qty')
    def _compute_product_cost_total(self):
        for order in self:
            self.check_items_expiration()
            order.product_cost = sum(line.row_total for line in order.manufacturing_order_line_ids) * order.product_qty

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

        # Adjust stock for the finished product

        # Generate and set the order reference only if it's not provided
        vals['name'] = self._generate_order_reference(vals)

        # Call the super method to handle the creation process with the possibly updated vals
        if 'bom_id' in vals and not vals.get('product_id'):
            bom = self.env['idil.bom'].browse(vals['bom_id'])
            if bom and bom.product_id:
                vals['product_id'] = bom.product_id.id
        order = super(ManufacturingOrder, self).create(vals)

        # Increase the product's stock quantity based on the BOM
        if order and order.bom_id and order.bom_id.product_id:
            product = order.bom_id.product_id
            product.stock_quantity += order.product_qty
            product.write({'stock_quantity': product.stock_quantity})  # Use write to save changes

        # Attempt to adjust stock levels
        try:

            for line in order.manufacturing_order_line_ids:
                if line.item_id and line.quantity:  # Ensure there's an item and a quantity before adjusting
                    # Adjust stock by the negative of the ordered quantity to decrease stock
                    line.item_id.adjust_stock(line.quantity)
        except ValidationError as e:
            # Directly re-raise the ValidationError with the original error message
            raise ValidationError(e.args[0])  # e.args[0] contains the error message string

        return order

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

    def write(self, vals):
        # Track original quantities for both the final product and items in the order lines
        self.check_items_expiration()
        original_product_quantities = {order.id: order.product_qty for order in self}
        original_item_quantities = {}
        for order in self:
            for line in order.manufacturing_order_line_ids:
                original_item_quantities[line.id] = line.quantity

        # Perform the actual update
        result = super(ManufacturingOrder, self).write(vals)

        for order in self:
            # Adjusting final product stock
            original_product_qty = original_product_quantities.get(order.id, 0)
            new_product_qty = order.product_qty
            product_qty_difference = new_product_qty - original_product_qty
            if product_qty_difference != 0 and order.bom_id and order.bom_id.product_id:
                product = order.bom_id.product_id
                new_stock_quantity = product.stock_quantity + product_qty_difference

                # Check if the new stock quantity would be negative
                if new_stock_quantity < 0:
                    raise ValidationError(
                        "Cannot adjust product stock for '{}' as it would result in a negative stock quantity.".format(
                            product.name)
                    )

                # Update the product's stock quantity if it's not negative
                product.write({'stock_quantity': new_stock_quantity})
            # Adjusting item stock based on line changes
            for line in order.manufacturing_order_line_ids:
                original_qty = original_item_quantities.get(line.id, 0)
                new_qty = line.quantity
                qty_difference = new_qty - original_qty
                if qty_difference != 0:
                    try:
                        # Assuming adjust_stock method exists for items to handle stock adjustments
                        line.item_id.adjust_stock(qty_difference)
                    except ValidationError as e:
                        raise ValidationError(e.args[0])

        return result

    def unlink(self):
        for order in self:
            _logger.info("Unlink called on ManufacturingOrder with IDs: %s", self.ids)
            if order.product_id and order.product_qty:
                new_qty = order.product_id.stock_quantity - order.product_qty
                if new_qty < 0:
                    raise ValidationError(
                        "Cannot delete order as it would result in negative stock for product %s." % order.product_id.name)
                order.product_id.write({'stock_quantity': new_qty})
        return super(ManufacturingOrder, self).unlink()


class ManufacturingOrderLine(models.Model):
    _name = 'idil.manufacturing.order.line'
    _description = 'Manufacturing Order Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    manufacturing_order_id = fields.Many2one('idil.manufacturing.order', string='Manufacturing Order', required=True,
                                             tracking=True)
    item_id = fields.Many2one('idil.item', string='Item', required=True, tracking=True)
    quantity_bom = fields.Float(string='Demand', required=True, tracking=True)

    quantity = fields.Float(string='Quantity Used', required=True, tracking=True)
    cost_price = fields.Float(string='Cost Price at Production', required=True, tracking=True, store=True)

    row_total = fields.Float(string='Row Total', compute='_compute_row_total', store=True)
    # New computed field for the difference between Demand and Quantity Used
    quantity_diff = fields.Float(string='Quantity Difference', compute='_compute_quantity_diff', store=True)

    @api.model
    def create(self, vals):
        result = super(ManufacturingOrderLine, self).create(vals)
        result._check_min_order_qty()
        return result

    def write(self, vals):
        result = super(ManufacturingOrderLine, self).write(vals)
        self._check_min_order_qty()
        return result

    def _check_min_order_qty(self):
        for line in self:
            if line.quantity <= line.item_id.min:
                # This is where you decide how to notify the user. For now, let's log a message.
                # Consider replacing this with a call to a custom notification system if needed.
                _logger.info(f"Attention: The quantity for item '{line.item_id.name}' in manufacturing order '{line.item_id.name}' is near or below the minimum order quantity.")

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
