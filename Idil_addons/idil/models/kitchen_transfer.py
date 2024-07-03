from odoo import models, fields, api, _
from odoo.exceptions import UserError


class KitchenTransfer(models.Model):
    _name = 'idil.kitchen.transfer'
    _description = 'Kitchen Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Transfer Reference', required=True, copy=False, default='New')
    transfer_date = fields.Datetime(string='Transfer Date', default=fields.Datetime.now, required=True, tracking=True)
    kitchen_id = fields.Many2one('idil.kitchen', string='Kitchen', required=True, tracking=True)
    transferred_by = fields.Many2one('res.users', string='Transferred By', default=lambda self: self.env.user,
                                     required=True, tracking=True)
    transfer_line_ids = fields.One2many('idil.kitchen.transfer.line', 'transfer_id', string='Transfer Lines',
                                        tracking=True)

    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('idil.kitchen.transfer') or _('New')

        # Check and update item quantities
        self._update_item_quantities(vals.get('transfer_line_ids', []), 'create')

        return super(KitchenTransfer, self).create(vals)

    def write(self, vals):
        if 'transfer_line_ids' in vals:
            self._update_item_quantities(vals['transfer_line_ids'], 'write')

        return super(KitchenTransfer, self).write(vals)

    def _update_item_quantities(self, transfer_lines, operation_type):
        for line in transfer_lines:
            if line[0] == 0:  # New line
                item_id = line[2].get('item_id')
                quantity = line[2].get('quantity')
                if item_id and quantity:
                    item = self.env['idil.item'].browse(item_id)
                    if item.quantity < quantity:
                        raise UserError(_('Not enough quantity for item: %s' % item.name))
                    item.quantity -= quantity
            elif line[0] == 1:  # Updated line
                existing_line = self.env['idil.kitchen.transfer.line'].browse(line[1])
                new_quantity = line[2].get('quantity')
                if existing_line and new_quantity:
                    diff_quantity = new_quantity - existing_line.quantity
                    item = existing_line.item_id
                    if diff_quantity > 0:  # Increasing quantity
                        if item.quantity < diff_quantity:
                            raise UserError(_('Not enough quantity for item: %s' % item.name))
                        item.quantity -= diff_quantity
                    elif diff_quantity < 0:  # Decreasing quantity
                        item.quantity -= diff_quantity  # diff_quantity is negative, so this increases item.quantity


class KitchenTransferLine(models.Model):
    _name = 'idil.kitchen.transfer.line'
    _description = 'Kitchen Transfer Line'

    transfer_id = fields.Many2one('idil.kitchen.transfer', string='Transfer Reference', required=True,
                                  ondelete='cascade')
    item_id = fields.Many2one('idil.item', string='Item', required=True)
    quantity = fields.Float(string='Quantity', required=True)
